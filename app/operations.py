"""Secondary operations: transactional event outbox, inbox and bounded delegation."""
import asyncio
import hashlib
import logging
from dataclasses import replace
from datetime import datetime, timedelta

from fastapi import HTTPException
from sqlalchemy import and_, func, or_, select, update, union_all, literal
from sqlalchemy.dialects.sqlite import insert

from .models import (Delegation, DelegationAudit, EscalationRecord, Notification, OperationOutbox,
    PortalUser, RequestAssignment, RequestEvent, RequestRecord, RequestReferral, RequestWorkflow, UserOrganization)
from .time_policy import utc_now, as_utc, utc_stamp
from .utils import json_dumps, json_loads
from . import workflow_policy as policy

EVENTS = {
    'PUB_PREPARE': ('Ders sürümü yayınlamaya hazır', 'Hazırlanan katalog sürümünü kontrol edip açık yayın işlemini gerçekleştirin.', 'unit'),
    'DEV_CREATED': ('Eğitim geliştirme işi açıldı', 'Kaynak ihtiyacı inceleyerek tasarım çalışmasına başlayın.', 'unit'),
    'DEV_SUBMIT_REVIEW': ('Eğitim tasarımı inceleme bekliyor', 'Kaydedilen tasarım sürümünü inceleyin.', 'unit'),
    'DEV_REQUEST_REVISION': ('Tasarım için düzeltme istendi', 'İnceleme açıklamasına göre tasarımı güncelleyin.', 'unit'),
    'DEV_ASSIGN': ('Eğitim geliştirme sorumluluğu güncellendi', 'Beklenen tasarım işlemini inceleyin.', 'unit'),
    'REQUEST_INFO': ('Ek bilginiz bekleniyor', 'İstenen bilgileri talep detayından tamamlayın.', 'owner'),
    'ASSIGN': ('Size bir talep atandı', 'Talebi inceleyerek beklenen işlemi gerçekleştirin.', 'assignee'),
    'REFER': ('Biriminize talep yönlendirildi', 'Kapsamı değerlendirmek için talebi açın.', 'unit'),
    'REVIEW_ADVANCE': ('Talep değerlendirmesi tamamlandı', 'Biriminize yönlendirilen talebi inceleyin.', 'unit'),
    'PLAN_CREATED': ('Çözüm planı hazırlandı', 'Planı inceleyin; çözüm gerçekleştiğinde sonucu bildirebilirsiniz.', 'owner_assignee'),
    'PLAN_UPDATED': ('Çözüm planı güncellendi', 'Talebinizin güncel çözüm planını inceleyin.', 'owner_assignee'),
    'RESOLVE': ('Talep çözüme ulaştı', 'Sonuç ve açıklama talep detayında kayıtlı.', 'owner'),
    'REOPEN': ('Talep yeniden incelemede', 'Yeniden açılan ihtiyacı değerlendirin.', 'unit_owner'),
    'RETURN_REVIEW': ('Talep yeniden ihtiyaç analizinde', 'Geri gönderme açıklamasını ve beklenen işlemi inceleyin.', 'unit_owner'),
    'ANALYSIS_FAILED': ('Analiz tamamlanamadı', 'Talep korundu. Uygun işlem alanından analizi yeniden deneyebilirsiniz.', 'unit_owner'),
    'ANALYSIS_COMPLETED': ('Değerlendirilecek analiz hazır', 'Güncel analiz sonucunu inceleyin.', 'unit'),
    'ESCALATED': ('Tanımlı işlem süresi aşıldı', 'Sorumluluğunuza bildirilen talebi inceleyin.', 'explicit'),
}


def install_schema(bind):
    # create_all preserves existing tables; install additive indexes explicitly too.
    for index in Notification.__table__.indexes:
        index.create(bind, checkfirst=True)


def capture_event(db, entry, action, details):
    """Small immutable envelope; notification rendering/delivery stays outside workflow."""
    if action not in EVENTS or action == 'REVIEW_ADVANCE' and entry.status != 'REFERRED':
        return
    if action in ('ANALYSIS_FAILED', 'ANALYSIS_COMPLETED') and entry.status != 'IN_REVIEW':
        return
    flow = db.get(RequestWorkflow, entry.request_id)
    referral = db.get(RequestReferral, entry.request_id)
    scope = policy.owner_scope(entry.status, referral.department if referral and referral.active else None)
    if action.startswith(('DEV_', 'PUB_')):
        scope = details['development_scope']
    assignment = db.get(RequestAssignment, entry.request_id)
    assignee = details.get('assignee_id') if 'assignee_id' in details else (details.get('after') or {}).get('assignee', {})
    if isinstance(assignee, dict):
        assignee = assignee.get('id')
    if 'assignee_id' not in details and 'after' not in details and assignee is None and assignment and assignment.responsible_scope == scope:
        assignee = assignment.assignee_id
    owner = str(flow.owner_hash if flow else '').removeprefix('user:')
    db.add(OperationOutbox(event=entry, payload_json=json_dumps({'action': action, 'status': entry.status,
        'owner_id': int(owner) if owner.isdecimal() else None, 'scope': scope, 'assignee_id': assignee,
        'recipient_ids': details.get('recipient_ids', []), 'development_id': details.get('development_id'),
        'publication_id': details.get('publication_id')})))


def compatible(db, delegator, delegate):
    if not delegator or not delegate or not delegator.active or not delegate.active or delegator.id == delegate.id or delegator.role != delegate.role:
        return False
    # Existing role scope is mandatory. Known HR boundaries narrow it further.
    a, b = db.get(UserOrganization, delegator.id), db.get(UserOrganization, delegate.id)
    for field in ('organization', 'directorate', 'unit', 'chiefdom'):
        left, right = getattr(a, field, None), getattr(b, field, None)
        if (left or right) and left != right:
            return False
    return True


def valid_delegation(db, row, actor_id=None):
    return bool(row and row.active and as_utc(row.start_at) <= utc_now() < as_utc(row.end_at)
        and (actor_id is None or row.delegate_id == actor_id)
        and compatible(db, db.get(PortalUser, row.delegator_id), db.get(PortalUser, row.delegate_id)))


def delegation_scope(db, row, record, flow):
    if not valid_delegation(db, row) or not flow:
        return False
    user = db.get(PortalUser, row.delegator_id)
    if user.role == 'EMPLOYEE':
        if flow.owner_hash != f'user:{user.id}':
            return False
        ctx = policy.context(db, record, flow)
        from .analysis_pipeline import latest_run, analysis_actions
        last = latest_run(db, record.id)
        retry = last and last.status == 'FAILED' and analysis_actions(db, record, flow, user.role)
        return bool(retry or any(item['code'] != 'REOPEN' for item in policy.available_actions(ctx, user.role)))
    ctx = policy.context(db, record, flow, include_review=False)
    return bool(ctx['scope'] == user.role and ctx['assignee'] and ctx['assignee']['id'] == user.id)


def acting_principal(db, principal, delegation_id, request_id):
    row = db.get(Delegation, delegation_id)
    record, flow = db.get(RequestRecord, request_id), db.get(RequestWorkflow, request_id)
    if not record or not valid_delegation(db, row, principal.user_id) or not delegation_scope(db, row, record, flow):
        raise HTTPException(403, 'Bu talep için geçerli ve kapsamı uygun bir vekâletiniz yok.')
    owner = db.get(PortalUser, row.delegator_id)
    return replace(principal, delegation={'id': row.id, 'delegator_id': owner.id,
        'delegator_name': owner.display_name, 'acting_user_id': principal.user_id,
        'acting_user_name': principal.display_name})


def delegation_payload(db, row):
    a, b = db.get(PortalUser, row.delegator_id), db.get(PortalUser, row.delegate_id)
    state = 'revoked' if not row.active else 'ended' if as_utc(row.end_at) <= utc_now() else 'scheduled' if as_utc(row.start_at) > utc_now() else 'active' if valid_delegation(db, row) else 'ineligible'
    return {'id': row.id, 'delegator_id': row.delegator_id, 'delegate_id': row.delegate_id,
        'delegator_name': a.display_name, 'delegate_name': b.display_name, 'start_at': utc_stamp(row.start_at),
        'end_at': utc_stamp(row.end_at), 'state': state, 'reason': row.reason,
        'history': [{'action': event.action, 'at': utc_stamp(event.created_at), 'actor_id': event.actor_id}
                    for event in db.scalars(select(DelegationAudit).where(DelegationAudit.delegation_id == row.id).order_by(DelegationAudit.id))]}


def delegation_options(db, principal):
    user = db.get(PortalUser, principal.user_id)
    return [{'id': other.id, 'display_name': other.display_name} for other in db.scalars(
        select(PortalUser).where(PortalUser.active.is_(True), PortalUser.role == principal.role).order_by(PortalUser.display_name))
        if compatible(db, user, other)]


def create_delegation(db, principal, payload):
    owner, delegate = db.get(PortalUser, principal.user_id), db.get(PortalUser, payload.delegate_id)
    if not compatible(db, owner, delegate):
        raise HTTPException(422, 'Vekil, rolü ve kayıtlı birim kapsamı uyumlu aktif bir kullanıcı olmalıdır.')
    if payload.end_at <= payload.start_at or payload.end_at <= utc_now():
        raise HTTPException(422, 'Vekâlet bitişi başlangıçtan ve şu andan sonra olmalıdır.')
    # Serialize overlapping-window checks without changing the account.
    db.execute(update(PortalUser).where(PortalUser.id == owner.id).values(active=PortalUser.active))
    overlap = db.scalar(select(Delegation.id).where(Delegation.delegator_id == owner.id, Delegation.active.is_(True),
        Delegation.start_at < payload.end_at, Delegation.end_at > payload.start_at))
    if overlap:
        db.rollback()
        raise HTTPException(409, 'Bu tarih aralığında başka bir vekâletiniz bulunuyor.')
    row = Delegation(delegator_id=owner.id, delegate_id=delegate.id, start_at=payload.start_at,
        end_at=payload.end_at, created_by=owner.id, reason=payload.reason)
    db.add(row); db.flush()
    db.add(DelegationAudit(delegation_id=row.id, actor_id=owner.id, action='CREATED', details_json=json_dumps({
        'delegator_name': owner.display_name, 'delegate_name': delegate.display_name,
        'start_at': utc_stamp(row.start_at), 'end_at': utc_stamp(row.end_at), 'reason': row.reason})))
    db.commit()
    return delegation_payload(db, row)


def revoke_delegation(db, principal, identifier):
    row = db.get(Delegation, identifier)
    if not row or row.delegator_id != principal.user_id:
        raise HTTPException(404, 'Vekâlet bulunamadı.')
    changed = db.execute(update(Delegation).where(Delegation.id == identifier, Delegation.active.is_(True)).values(active=False))
    if changed.rowcount:
        db.add(DelegationAudit(delegation_id=identifier, actor_id=principal.user_id, action='REVOKED'))
    db.commit()
    return {'revoked': True}


def can_see(db, user, request_id):
    from .workflow import audience_scope
    if db.scalar(select(RequestRecord.id).outerjoin(RequestWorkflow).where(RequestRecord.id == request_id,
        audience_scope(f'user:{user.id}', user.role != 'EMPLOYEE', user.role))):
        return True
    record, flow = db.get(RequestRecord, request_id), db.get(RequestWorkflow, request_id)
    return bool(record and any(delegation_scope(db, row, record, flow) for row in db.scalars(select(Delegation).where(Delegation.delegate_id == user.id))))


def notification_query(principal):
    # Recipient filtering is mandatory even when broad request privileges exist.
    return select(Notification).where(Notification.recipient_id == principal.user_id)


def link_delegation(db, user, request_id):
    record, flow = db.get(RequestRecord, request_id), db.get(RequestWorkflow, request_id)
    if not record:
        return None
    for row in db.scalars(select(Delegation).where(Delegation.delegate_id == user.id, Delegation.active.is_(True)).order_by(Delegation.id)):
        if delegation_scope(db, row, record, flow):
            return row.id
    return None


def _request_notifications(db, principal, offset, limit, identifiers=None):
    user = db.get(PortalUser, principal.user_id)
    query = notification_query(principal)
    if identifiers is not None:
        query = query.where(Notification.id.in_(identifiers))
    rows = db.scalars(query.order_by(Notification.id.desc()).offset(offset).limit(limit))
    items = []
    for row in rows:
        visible = can_see(db, user, row.request_id)
        development_id, development_delegation, publication_id = None, None, None
        if row.type.startswith('PUB_'):
            from .models import PublicationEvent, CourseVersion, DevelopmentItem
            from .publishing import inbox_items
            from .development import visible as development_visible
            event = db.scalar(select(PublicationEvent).where(PublicationEvent.request_event_id == row.source_event_id))
            version = db.get(CourseVersion, event.version_id) if event else None
            item = db.get(DevelopmentItem, version.source_development_id) if version else None
            visible = bool(item and development_visible(db,item,principal))
            if visible:
                publication_id = version.id
                development_delegation = next((value['delegation']['id'] for value in inbox_items(db,principal,identifiers=[version.id])
                    if value['publication_id']==version.id and value['delegation']),None)
        if row.type.startswith('DEV_'):
            from .models import DevelopmentEvent, DevelopmentItem
            from .development import visible as development_visible, inbox_items
            event = db.scalar(select(DevelopmentEvent).where(DevelopmentEvent.request_event_id == row.source_event_id))
            item = db.get(DevelopmentItem, event.item_id) if event else None
            visible = bool(item and development_visible(db, item, principal))
            if visible:
                development_id = item.id
                development_delegation = next((value['delegation']['id'] for value in inbox_items(db, principal,identifiers=[item.id])
                    if value['development_id'] == item.id and value['delegation']), None)
        items.append({'id': row.id, 'title': row.title if visible else 'Talep erişiminiz değişti',
            'message': row.message if visible else 'Bu kaydın güncel içeriğine erişiminiz bulunmuyor.',
            'request_id': row.request_id if visible else None, 'created_at': utc_stamp(row.created_at),
            'development_id': development_id,
            'publication_id': publication_id,
            'delegation_id': development_delegation if development_id or publication_id else link_delegation(db, user, row.request_id) if visible else None,
            'read_at': utc_stamp(row.read_at), 'importance': row.importance if visible else 'normal'})
    return {'items': items, 'offset': offset, 'limit': limit,
        'total': db.scalar(select(func.count()).select_from(Notification).where(Notification.recipient_id == principal.user_id))}


def notifications(db, principal, offset, limit):
    from .models import TrainingNotification
    from .training import notification_payload
    from .evaluation_models import EvaluationDelivery
    from .evaluation import notice_payload
    combined = union_all(
        select(Notification.id.label('id'), Notification.created_at.label('created_at'), literal('request').label('kind')).where(Notification.recipient_id == principal.user_id),
        select(TrainingNotification.id.label('id'), TrainingNotification.created_at.label('created_at'), literal('training').label('kind')).where(TrainingNotification.recipient_id == principal.user_id),
        select(EvaluationDelivery.id.label('id'),EvaluationDelivery.processed_at.label('created_at'),literal('evaluation').label('kind')).where(EvaluationDelivery.recipient_id==principal.user_id,EvaluationDelivery.processed_at.is_not(None))
    ).subquery()
    rows = db.execute(select(combined).order_by(combined.c.created_at.desc(),combined.c.id.desc(),combined.c.kind).offset(offset).limit(limit)).all()
    request_ids = [r.id for r in rows if r.kind == 'request']
    old = {r['id']: r for r in _request_notifications(db,principal,0,limit,request_ids)['items']} if request_ids else {}
    return {'items': [old[r.id] if r.kind == 'request' else notice_payload(db,db.get(EvaluationDelivery,r.id),principal) if r.kind=='evaluation' else notification_payload(db,db.get(TrainingNotification,r.id),principal) for r in rows],
        'total':db.scalar(select(func.count()).select_from(combined)), 'offset':offset, 'limit':limit}


def read_notification(db, principal, identifier=None):
    from .evaluation_models import EvaluationDelivery
    if identifier is None or str(identifier).startswith('evaluation:'):
        condition=[EvaluationDelivery.recipient_id==principal.user_id,EvaluationDelivery.processed_at.is_not(None)]
        if identifier is not None:
            value=str(identifier).split(':',1)[1]
            if not value.isdecimal(): raise HTTPException(422,'Geçersiz bildirim.')
            condition.append(EvaluationDelivery.id==int(value))
            if not db.scalar(select(EvaluationDelivery.id).where(*condition)): raise HTTPException(404,'Bildirim bulunamadı.')
        db.execute(update(EvaluationDelivery).where(*condition,EvaluationDelivery.read_at.is_(None)).values(read_at=utc_now()))
        if identifier is not None:
            db.commit();return {'read':True}
    if identifier is not None:
        try: identifier=int(identifier)
        except ValueError: raise HTTPException(422,'Geçersiz bildirim.')
    from .models import TrainingNotification
    if identifier is None or identifier < 0:
        conditions = [TrainingNotification.recipient_id == principal.user_id]
        if identifier is not None:
            conditions.append(TrainingNotification.id == -identifier)
            if not db.scalar(select(TrainingNotification.id).where(*conditions)):
                raise HTTPException(404,'Bildirim bulunamadı.')
        db.execute(update(TrainingNotification).where(*conditions,TrainingNotification.read_at.is_(None)).values(read_at=utc_now()))
        if identifier is not None:
            db.commit()
            return {'read':True}
    condition = [Notification.recipient_id == principal.user_id]
    if identifier is not None:
        condition.append(Notification.id == identifier)
        if not db.scalar(select(Notification.id).where(*condition)):
            raise HTTPException(404, 'Bildirim bulunamadı.')
    db.execute(update(Notification).where(*condition, Notification.read_at.is_(None)).values(read_at=utc_now()))
    db.commit()
    return {'read': True}


def translate_event(db, outbox):
    envelope = json_loads(outbox.payload_json, {})
    action = envelope['action']
    if action not in EVENTS:
        return
    entry = db.get(RequestEvent, outbox.event_id)
    title, message, target = EVENTS[action]
    recipients = set()
    if 'owner' in target and envelope.get('owner_id'):
        recipients.add(envelope['owner_id'])
    if 'assignee' in target and envelope.get('assignee_id'):
        recipients.add(envelope['assignee_id'])
    if 'unit' in target:
        if envelope.get('assignee_id'):
            recipients.add(envelope['assignee_id'])
        elif envelope.get('scope') in policy.MANAGER_ROLES:
            recipients.update(db.scalars(select(PortalUser.id).where(PortalUser.role == envelope['scope'], PortalUser.active.is_(True))))
    if target == 'explicit':
        recipients.update(envelope.get('recipient_ids', []))
    record, flow = db.get(RequestRecord, entry.request_id), db.get(RequestWorkflow, entry.request_id)
    development = None
    if envelope.get('development_id'):
        from .models import DevelopmentItem
        development = db.get(DevelopmentItem, envelope['development_id'])
    for row in db.scalars(select(Delegation).where(Delegation.delegator_id.in_(recipients), Delegation.active.is_(True))):
        eligible = (valid_delegation(db, row) and development.assignee_id == row.delegator_id) if development else delegation_scope(db, row, record, flow)
        if eligible:
            recipients.add(row.delegate_id)
    delivered_recipients = set()
    for recipient in sorted(recipients):
        user = db.get(PortalUser, recipient)
        if not user or not user.active or not can_see(db, user, entry.request_id):
            continue
        if development:
            from .development import visible as development_visible
            if not development_visible(db, development, user):
                continue
        db.execute(insert(Notification).values(recipient_id=recipient, request_id=entry.request_id,
            source_event_id=entry.id, type=action, title=title, message=message,
            importance='warning' if action in ('ANALYSIS_FAILED', 'ESCALATED') else 'normal', created_at=utc_now())
            .on_conflict_do_nothing(index_elements=['source_event_id', 'recipient_id']))
        delivered_recipients.add(recipient)
    # Optional external channels are queued after the durable in-app record.
    # Their failure is isolated inside communication.dispatch_deliveries and
    # can never roll back the request workflow or the in-app notification.
    try:
        from .communication import enqueue_external_deliveries
        enqueue_external_deliveries(db, event_id=entry.id, event_type=action,
                                    recipient_ids=delivered_recipients,
                                    context={'request_id': entry.request_id})
    except Exception:
        # Configuration or template errors must not make a business event
        # retry forever; the in-app notification remains authoritative.
        logging.getLogger(__name__).warning('Optional communication queue skipped: event=%s', entry.id)


def dispatch_events(factory):
    with factory() as db:
        identifiers = list(db.scalars(select(OperationOutbox.event_id).where(OperationOutbox.processed_at.is_(None),
            or_(OperationOutbox.retry_at.is_(None), OperationOutbox.retry_at <= utc_now())).order_by(OperationOutbox.event_id).limit(50)))
    for identifier in identifiers:
        try:
            with factory() as db:
                changed = db.execute(update(OperationOutbox).where(OperationOutbox.event_id == identifier,
                    OperationOutbox.processed_at.is_(None)).values(attempts=OperationOutbox.attempts + 1))
                if not changed.rowcount:
                    continue
                translate_event(db, db.get(OperationOutbox, identifier))
                db.execute(update(OperationOutbox).where(OperationOutbox.event_id == identifier).values(processed_at=utc_now()))
                db.commit()
        except Exception as error:
            logging.getLogger(__name__).warning('Notification delivery pending: event=%s type=%s', identifier, type(error).__name__)
            with factory() as db:
                db.execute(update(OperationOutbox).where(OperationOutbox.event_id == identifier,
                    OperationOutbox.processed_at.is_(None)).values(retry_at=utc_now()+timedelta(seconds=30)))
                db.commit()


def required_actions(db, record, flow, principal):
    from .analysis_pipeline import latest_run, analysis_actions
    ctx = policy.context(db, record, flow)
    last = latest_run(db, record.id)
    if last and last.status in ('PENDING', 'PROCESSING'):
        return []
    actions = policy.available_actions(ctx, principal.role)
    assigned_to_me = not ctx['assignee'] or ctx['assignee']['id'] == (principal.delegation or {}).get('delegator_id', principal.user_id)
    owns = ctx['scope'] == principal.role and assigned_to_me
    if principal.role == 'EMPLOYEE':
        owns = flow and flow.owner_hash == principal.token_hash
    if not owns:
        return []
    if last and last.status == 'FAILED':
        return analysis_actions(db, record, flow, principal.role)
    excluded = {'REOPEN', 'RETURN_REVIEW', 'ASSIGN'}
    ordered = policy.INBOX_ACTION_ORDER.get(ctx['state'], ())
    return sorted([item for item in actions if item['code'] not in excluded],
        key=lambda item: ordered.index(item['code']) if item['code'] in ordered else len(ordered))


def inbox(db, principal, offset=0, limit=20):
    from .inbox_query import inbox as sql_inbox
    return sql_inbox(db, principal, offset, limit)


def delegation_lifecycle(db):
    started = select(DelegationAudit.id).where(DelegationAudit.delegation_id == Delegation.id, DelegationAudit.action == 'STARTED').exists()
    ended = select(DelegationAudit.id).where(DelegationAudit.delegation_id == Delegation.id, DelegationAudit.action == 'ENDED').exists()
    pending = or_(and_(Delegation.end_at <= utc_now(), ~ended), and_(Delegation.end_at > utc_now(), ~started))
    for row in db.scalars(select(Delegation).where(Delegation.active.is_(True), Delegation.start_at <= utc_now(), pending)):
        action = 'ENDED' if as_utc(row.end_at) <= utc_now() else 'STARTED'
        if action == 'STARTED' and not valid_delegation(db, row):
            continue
        db.execute(insert(DelegationAudit).values(delegation_id=row.id, action=action, created_at=utc_now(),
            details_json=json_dumps({'effective_at': utc_stamp(row.end_at if action == 'ENDED' else row.start_at)}))
            .on_conflict_do_nothing(index_elements=['delegation_id', 'action']))
    db.commit()


def check_escalations(db):
    if not policy.SLA_TARGETS:
        return
    from .workflow_core import aging
    from .process import add_process_event
    for record, flow in db.execute(select(RequestRecord, RequestWorkflow).join(RequestWorkflow).where(RequestWorkflow.status != 'RESOLVED')):
        ctx = policy.context(db, record, flow, include_review=False)
        target = policy.sla_target(ctx)
        if not target or not target.get('recipient_user_ids'):
            continue
        age = aging(db, record, flow, ctx)
        if not age['sla'] or age['sla']['state'] != 'overdue':
            continue
        recipients = [identifier for identifier in target['recipient_user_ids'] if (user := db.get(PortalUser, identifier))
                      and user.active and can_see(db, user, record.id)]
        if not recipients:
            continue
        key = hashlib.sha256(json_dumps(target).encode()).hexdigest()
        start = datetime.fromisoformat(age['stage_started_at'].replace('Z', '+00:00'))
        if db.scalar(select(EscalationRecord.id).where(EscalationRecord.request_id == record.id,
            EscalationRecord.policy_key == key, EscalationRecord.stage_started_at == start)):
            continue
        # Same request version lock serializes escalation with stage transitions.
        locked = db.execute(update(RequestWorkflow).where(RequestWorkflow.request_id == record.id,
            RequestWorkflow.version == flow.version).values(version=RequestWorkflow.version))
        if not locked.rowcount:
            db.rollback(); continue
        if db.scalar(select(EscalationRecord.id).where(EscalationRecord.request_id == record.id,
            EscalationRecord.policy_key == key, EscalationRecord.stage_started_at == start)):
            db.rollback(); continue
        entry = add_process_event(db, request_id=record.id, status=flow.status, actor='SYSTEM',
            note='Tanımlı işlem süresi aşıldı; yapılandırılmış sorumlu kullanıcılara bildirildi.',
            action='ESCALATED', from_status=flow.status, details={'recipient_ids': recipients, 'policy_key': key})
        db.flush()
        db.add(EscalationRecord(request_id=record.id, policy_key=key, stage_started_at=start, event_id=entry.id))
        db.commit()


async def worker(factory):
    next_escalation_check = utc_now()
    while True:
        try:
            dispatch_events(factory)
            with factory() as db:
                from .evaluation import dispatch as dispatch_evaluations
                dispatch_evaluations(db)
                from .communication import dispatch_deliveries
                dispatch_deliveries(factory)
                delegation_lifecycle(db)
                if utc_now() >= next_escalation_check:
                    check_escalations(db)
                    next_escalation_check = utc_now() + timedelta(seconds=30)
        except Exception as error:
            logging.getLogger(__name__).error('Operations worker: %s', type(error).__name__)
        await asyncio.sleep(3)
