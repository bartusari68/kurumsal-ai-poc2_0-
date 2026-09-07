"""Version-locked learning design records, using existing identity and operations."""
from dataclasses import replace
from datetime import datetime, time, timezone
from fastapi import HTTPException
from sqlalchemy import select, update, func
from .models import (DevelopmentItem as Item, DevelopmentOutcome as Outcome, DevelopmentModule as Module,
    DevelopmentTopic as Topic, DevelopmentEvent as Event, RequestRecord, RequestWorkflow, RequestReferral,
    RequestDecision, PortalUser, DocumentIndex, Course, Delegation)
from . import development_policy as policy
from .workflow_core import checked_user
from .time_policy import utc_now, utc_stamp, as_utc
from .utils import json_dumps, json_loads


def visible(db, item, principal):
    if principal.role == 'NEEDS_ANALYST':
        return True
    ref = db.get(RequestReferral, item.source_request_id)
    return bool(principal.role == item.responsible_unit and ref and ref.active and
                ref.training_need_confirmed and ref.department == principal.role)


def authorized_actor(db, item, principal, delegation_id=None):
    from .operations import valid_delegation
    if not visible(db, item, principal):
        raise HTTPException(404, 'Eğitim geliştirme çalışması bulunamadı.')
    if delegation_id is not None:
        row = db.get(Delegation, delegation_id)
        if not valid_delegation(db, row, principal.user_id) or item.assignee_id != row.delegator_id:
            raise HTTPException(403, 'Bu eğitim geliştirme işi için geçerli vekâletiniz yok.')
        owner = db.get(PortalUser, row.delegator_id)
        if owner.role != item.responsible_unit:
            raise HTTPException(403, 'Vekâlet bu sorumlu birimi kapsamıyor.')
        return replace(principal, delegation={'id': row.id, 'delegator_id': owner.id,
            'delegator_name': owner.display_name, 'acting_user_id': principal.user_id,
            'acting_user_name': principal.display_name})
    return principal


def can_act(db, item, principal):
    flow = db.get(RequestWorkflow, item.source_request_id)
    acting_id = (principal.delegation or {}).get('delegator_id', principal.user_id)
    return bool(visible(db, item, principal) and principal.role == item.responsible_unit and
        flow and flow.status in ('REFERRED', 'ACTION_PLANNED') and
        (item.assignee_id is None or item.assignee_id == acting_id))


def load(db, identifier, principal, delegation_id=None):
    item = db.get(Item, identifier)
    if not item:
        raise HTTPException(404, 'Eğitim geliştirme çalışması bulunamadı.')
    return item, authorized_actor(db, item, principal, delegation_id)


def source_draft(db, record, flow):
    from .analysis_pipeline import current_result, decision_is_current, latest_run
    from .learning import decision_support
    ref = db.get(RequestReferral, record.id)
    if not ref or not ref.active or not ref.training_need_confirmed or not flow or flow.status not in ('REFERRED', 'ACTION_PLANNED'):
        return None
    result = current_result(db, record, flow)
    support = decision_support(result, record.text)
    decision = db.scalar(select(RequestDecision).where(RequestDecision.request_id == record.id).order_by(RequestDecision.id.desc()).limit(1))
    if decision and not decision_is_current(db, decision, record, flow):
        return None
    if decision and (decision.outcome == 'REJECTED' or not decision.training_need_confirmed):
        return None
    course_id = decision.actual_course_id if decision else (support['brief']['existing_course'] or {}).get('course_id')
    missing = json_loads(decision.missing_topics_json, []) if decision else support['missing_topics']
    if course_id and not missing:
        return None
    if not decision and support['action'] not in ('NEW_COURSE', 'ENRICH_COURSE'):
        return None
    work_type = 'COURSE_ENRICHMENT' if course_id else 'NEW_COURSE'
    course = db.get(Course, course_id) if course_id else None
    if course_id and not course:
        return None
    index = db.scalar(select(DocumentIndex).where(DocumentIndex.course_id == course_id)) if course else None
    run = latest_run(db, record.id, completed=True)
    selected = next((entry for entry in result.get('courses', []) if entry.get('course_id') == course_id), {})
    fit = selected.get('fit') or {}
    needs = fit.get('requirements', [])
    source_hash = (decision.course_source_hash if decision else '') or next((entry['fingerprint']
        for entry in result.get('provenance', {}).get('source_fingerprints', []) if entry['course_id'] == course_id), '')
    return {'work_type': work_type, 'source_course_id': course_id,
        'source_course_hash': source_hash or (index.content_hash if index else ''), 'title': record.topic or support['brief']['title'],
        'summary': record.text, 'responsible_unit': ref.department,
        'brief': {'target_output': '', 'missing_topics': missing, 'change_notes': '',
                  'excess_notes': '\n'.join(json_loads(decision.excess_topics_json, [])) if decision else ''},
        'context': {'decision_id': decision.id if decision else None, 'analysis_run_id': run.id if run else None,
            'fit_percent': fit.get('percent', support['fit_percent'] if selected and result.get('courses', [])[0] == selected else None) if course else support['fit_percent'],
            'course_name': course.name if course else None,
            'covered_needs': [need['label'] for need in needs if need.get('status') == 'FULL'],
            'partial_needs': [need['label'] for need in needs if need.get('status') == 'PARTIAL'],
            'missing_topics': missing, 'suggested_outcomes': support['brief']['learning_objectives'],
            'suggestion_label': 'Önceki analizden başlangıç önerisi; kaydedilene kadar onaylanmış kazanım değildir.'}}


def request_links(db, record, flow, role):
    rows = db.scalars(select(Item).where(Item.source_request_id == record.id).order_by(Item.id.desc())).all()
    allowed = role == 'NEEDS_ANALYST' or role in policy.DEPARTMENTS
    rows = [row for row in rows if role not in policy.DEPARTMENTS or row.responsible_unit == role]
    draft = source_draft(db, record, flow) if role in policy.DEPARTMENTS else None
    if draft and draft['responsible_unit'] != role:
        draft = None
    if draft and any(row.work_type == draft['work_type'] and row.state not in policy.TERMINAL for row in rows):
        draft = None
    return {'items': [{'id': row.id, 'title': row.title, 'state_label': policy.STATES[row.state]['label'],
        'work_type_label': policy.WORK_TYPES[row.work_type], 'can_open': allowed} for row in rows],
        'create': {'work_type': draft['work_type'], 'label': policy.WORK_TYPES[draft['work_type']],
                   'source_course_id': draft['source_course_id']} if draft else None}


def artifacts(db, item):
    outcomes = [{'id': row.id, 'position': row.position, 'text': row.text,
        'created_at': utc_stamp(row.created_at), 'updated_at': utc_stamp(row.updated_at)}
        for row in db.scalars(select(Outcome).where(Outcome.item_id == item.id).order_by(Outcome.position))]
    modules = [{'id': row.id, 'position': row.position, 'title': row.title, 'description': row.description,
        'topics': [{'id': topic.id, 'position': topic.position, 'title': topic.title, 'description': topic.description}
            for topic in db.scalars(select(Topic).where(Topic.module_id == row.id).order_by(Topic.position))]}
        for row in db.scalars(select(Module).where(Module.item_id == item.id).order_by(Module.position))]
    return {'title': item.title, 'summary': item.summary, 'brief': json_loads(item.brief_json, {}),
            'outcomes': outcomes, 'modules': modules, 'content_revision': item.content_revision}


def summary(db, item):
    user = db.get(PortalUser, item.assignee_id) if item.assignee_id else None
    author = db.get(PortalUser, item.created_by)
    course = db.get(Course, item.source_course_id) if item.source_course_id else None
    age = lambda date: max(0, int((utc_now() - as_utc(date)).total_seconds()))
    return {'id': item.id, 'source_request_id': item.source_request_id, 'title': item.title,
        'work_type': item.work_type, 'work_type_label': policy.WORK_TYPES[item.work_type], 'state': item.state,
        'state_label': policy.STATES[item.state]['label'], 'next_action': policy.STATES[item.state]['next'],
        'version': item.version, 'content_revision': item.content_revision, 'responsible_unit': item.responsible_unit,
        'responsible_unit_label': policy.DEPARTMENTS[item.responsible_unit],
        'assignee': {'id': user.id, 'display_name': user.display_name} if user else None,
        'created_by': {'id': item.created_by, 'display_name': author.display_name},
        'source_course': {'id': course.id, 'name': course.name, 'source_hash': item.source_course_hash} if course else None,
        'target_date': item.target_date.date().isoformat() if item.target_date else None,
        'created_at': utc_stamp(item.created_at), 'updated_at': utc_stamp(item.updated_at),
        'aging': {'created_seconds': age(item.created_at), 'current_stage_seconds': age(item.stage_started_at)}}


def detail(db, item, principal):
    editable = can_act(db, item, principal)
    from .publishing import development_link
    return {**summary(db, item), **artifacts(db, item), 'source_context': json_loads(item.source_context_json, {}),
        'publication': development_link(db, item, principal),
        'can_edit': editable and item.state in policy.EDITABLE,
        'actions': policy.available(item, principal, editable), 'acting_delegation': principal.delegation,
        'assignment_options': [{'id': user.id, 'display_name': user.display_name} for user in db.scalars(
            select(PortalUser).where(PortalUser.active.is_(True), PortalUser.role == item.responsible_unit))] if editable else [],
        'history': [{'id': event.id, 'action': event.action,
            'label': policy.EVENT_LABELS.get(event.action, 'Geliştirme işlemi kaydedildi'),
            'actor_name': event.actor_name, 'at': utc_stamp(event.created_at), 'note': event.note,
            'from_label': policy.STATES[event.from_state]['label'] if event.from_state else None,
            'to_label': policy.STATES[event.to_state]['label'], 'content_revision': event.content_revision,
            'snapshot_available': event.snapshot_json != '{}', 'delegation': json_loads(event.delegation_json, {})}
            for event in db.scalars(select(Event).where(Event.item_id == item.id).order_by(Event.id))]}


def lock(db, item, expected):
    changed = db.execute(update(Item).where(Item.id == item.id, Item.version == expected).values(
        version=Item.version + 1, updated_at=utc_now()).execution_options(synchronize_session=False))
    if changed.rowcount != 1:
        db.rollback()
        raise HTTPException(409, 'Çalışma başka bir işlemde güncellendi. Taslağınızı koruyarak güncel kaydı açın.')
    db.refresh(item)


def audit(db, item, principal, action, old=None, note='', snapshot=False):
    request_event = None
    if action != 'EDIT':
        from .process import add_process_event
        flow = db.get(RequestWorkflow, item.source_request_id)
        label = policy.EVENT_LABELS[action]
        request_event = add_process_event(db, request_id=item.source_request_id, status=flow.status,
            actor=principal.role, principal=principal, note=f'{label}: Eğitim geliştirme #{item.id}. {note}'.strip(),
            action='DEV_' + action, details={'development_id': item.id,
                'development_scope': item.responsible_unit, 'assignee_id': item.assignee_id})
        db.flush()
    db.add(Event(item_id=item.id, actor_id=principal.user_id, actor_name=principal.display_name,
        action=action, from_state=old, to_state=item.state, version=item.version,
        content_revision=item.content_revision, note=note, request_event_id=request_event.id if request_event else None,
        snapshot_json=json_dumps(artifacts(db, item)) if snapshot else '{}',
        delegation_json=json_dumps(principal.delegation or {})))


def create(db, principal, payload):
    from .workflow import owned_request
    from .workflow_policy import context
    if principal.role not in policy.DEPARTMENTS:
        raise HTTPException(403, 'Eğitim geliştirme işini sorumlu eğitim tasarım birimi oluşturabilir.')
    record, flow = owned_request(db, payload.source_request_id, principal.token_hash, admin=True, role=principal.role)
    # No-op request CAS serializes creation with request routing and decision changes.
    changed = db.execute(update(RequestWorkflow).where(RequestWorkflow.request_id == record.id,
        RequestWorkflow.version == payload.expected_request_version).values(version=RequestWorkflow.version))
    if changed.rowcount != 1:
        raise HTTPException(409, 'Kaynak talep güncellendi. Talebi yeniden açın.')
    db.expire_all()
    db.refresh(flow)
    draft = source_draft(db, record, flow)
    if not draft or draft['work_type'] != payload.work_type or draft['source_course_id'] != payload.source_course_id:
        raise HTTPException(422, 'İş türü veya ders bağlantısı doğrulanmış güncel ihtiyaca uymuyor.')
    ctx = context(db, record, flow)
    if not ctx['analysis_review_ready'] or ctx['scope'] != principal.role or ctx['assignee'] and ctx['assignee']['id'] != principal.user_id:
        raise HTTPException(403, 'Bu talebin güncel sorumlusu eğitim geliştirme işini başlatmalıdır.')
    existing = db.scalar(select(Item).where(Item.source_request_id == record.id, Item.work_type == payload.work_type,
        Item.state.not_in(policy.TERMINAL)))
    if existing:
        return detail(db, existing, principal)
    item = Item(source_request_id=record.id, work_type=draft['work_type'], title=draft['title'], summary=draft['summary'],
        responsible_unit=draft['responsible_unit'], assignee_id=ctx['assignee']['id'] if ctx['assignee'] else None,
        source_course_id=draft['source_course_id'], source_course_hash=draft['source_course_hash'],
        source_context_json=json_dumps(draft['context']), brief_json=json_dumps(draft['brief']), created_by=principal.user_id)
    db.add(item); db.flush(); audit(db, item, principal, 'CREATED', snapshot=True)
    db.commit()
    return detail(db, item, principal)


def sync_rows(db, model, owner_field, owner_id, values, fields):
    existing = {row.id: row for row in db.scalars(select(model).where(getattr(model, owner_field) == owner_id))}
    ids = [value.id for value in values if value.id is not None]
    if len(ids) != len(set(ids)) or not set(ids).issubset(existing):
        raise HTTPException(422, 'İçerik kimliği bu çalışmaya ait değil veya tekrar ediyor.')
    result = []
    for position, value in enumerate(values, 1):
        row = existing.pop(value.id) if value.id is not None else model(**{owner_field: owner_id})
        for field in fields:
            setattr(row, field, getattr(value, field))
        row.position = position
        if model is Outcome:
            row.updated_at = utc_now()
        db.add(row); db.flush(); result.append(row)
    for row in existing.values():
        if model is Module:
            for topic in db.scalars(select(Topic).where(Topic.module_id == row.id)):
                db.delete(topic)
            db.flush()
        db.delete(row)
    db.flush()
    return result


def edit(db, item, principal, payload):
    if not can_act(db, item, principal) or item.state not in policy.EDITABLE:
        raise HTTPException(403, 'Bu aşamada tasarım içeriğini düzenleme yetkiniz yok.')
    lock(db, item, payload.expected_version)
    item.title, item.summary, item.brief_json = payload.title, payload.summary, json_dumps(payload.brief.model_dump())
    item.content_revision += 1
    sync_rows(db, Outcome, 'item_id', item.id, payload.outcomes, ('text',))
    modules = sync_rows(db, Module, 'item_id', item.id, payload.modules, ('title', 'description'))
    for module, value in zip(modules, payload.modules):
        sync_rows(db, Topic, 'module_id', module.id, value.topics, ('title', 'description'))
    db.flush(); audit(db, item, principal, 'EDIT', item.state)
    db.commit()
    return detail(db, item, principal)


def act(db, item, principal, payload):
    allowed = {action['code']: action for action in policy.available(item, principal, can_act(db, item, principal))}
    rule = allowed.get(payload.action)
    if not rule:
        raise HTTPException(422, 'Bu aşamada bu işlem için yetkiniz yok.')
    lock(db, item, payload.expected_version)
    data = artifacts(db, item)
    checks = {'summary': bool(item.summary.strip()), 'target_output': bool(data['brief'].get('target_output', '').strip()),
        'outcomes': bool(data['outcomes']), 'modules': bool(data['modules']) and all(module['topics'] for module in data['modules']),
        'note': len(payload.note.strip()) >= 3,
        'enrichment_changes': item.work_type != 'COURSE_ENRICHMENT' or bool(data['brief'].get('change_notes', '').strip())}
    if 'review_snapshot' in rule['required']:
        reviewed = db.scalar(select(Event).where(Event.item_id == item.id, Event.action == 'SUBMIT_REVIEW').order_by(Event.id.desc()).limit(1))
        checks['review_snapshot'] = bool(reviewed and reviewed.content_revision == item.content_revision and
                                         json_loads(reviewed.snapshot_json, {}) == data)
    labels = {'summary': 'ihtiyaç özeti', 'target_output': 'hedeflenen çıktı', 'outcomes': 'en az bir kazanım',
        'modules': 'her modülde en az bir konu', 'note': 'en az 3 karakter açıklama',
        'enrichment_changes': 'değişiklik kapsamı', 'review_snapshot': 'güncel inceleme sürümü'}
    missing = [labels[key] for key in rule['required'] if not checks.get(key)]
    if missing:
        raise HTTPException(422, 'İşlem için gerekli: ' + ', '.join(missing))
    old = item.state
    if payload.action == 'ASSIGN':
        checked_user(db, payload.assignee_id, item.responsible_unit)
        item.assignee_id = payload.assignee_id
        item.target_date = datetime.combine(payload.target_date, time.min, tzinfo=timezone.utc) if payload.target_date else None
    if rule['target']:
        item.state, item.stage_started_at = rule['target'], utc_now()
    db.flush(); audit(db, item, principal, payload.action, old, payload.note, snapshot=bool(rule['target']))
    db.commit()
    return detail(db, item, principal)


def query(principal):
    stmt = select(Item)
    if principal.role == 'NEEDS_ANALYST':
        return stmt
    if principal.role not in policy.DEPARTMENTS:
        return stmt.where(False)
    return stmt.where(Item.responsible_unit == principal.role, Item.source_request_id.in_(select(RequestReferral.request_id).where(
        RequestReferral.department == principal.role, RequestReferral.active.is_(True), RequestReferral.training_need_confirmed.is_(True))))


def queue(db, principal, offset, limit):
    stmt = query(principal)
    return {'items': [summary(db, item) for item in db.scalars(stmt.order_by(Item.updated_at.desc(), Item.id.desc()).offset(offset).limit(limit))],
        'total': db.scalar(select(func.count()).select_from(stmt.subquery())), 'offset': offset, 'limit': limit}


def inbox_items(db, principal):
    from .operations import valid_delegation
    rows = db.scalars(query(principal).where(Item.state.not_in(policy.TERMINAL)))
    items = []
    for item in rows:
        actor = principal
        if not can_act(db, item, actor):
            delegation = next((row for row in db.scalars(select(Delegation).where(Delegation.delegator_id == item.assignee_id,
                Delegation.delegate_id == principal.user_id)) if valid_delegation(db, row, principal.user_id)), None)
            if not delegation:
                continue
            actor = authorized_actor(db, item, principal, delegation.id)
        if not can_act(db, item, actor):
            continue
        row = summary(db, item)
        items.append({**row, 'kind': 'development', 'development_id': item.id, 'request_id': item.source_request_id,
            'topic': item.title, 'text': item.summary[:180], 'action_required': row['next_action'], 'fit_percent': None,
            'delegation': actor.delegation, 'unread': False})
    return items
