"""Version-locked session operations; local notifications commit with the event."""
from dataclasses import replace
from datetime import datetime, time, timedelta, timezone
from fastapi import HTTPException
from sqlalchemy import select, update, func, or_, and_
from sqlalchemy.dialects.sqlite import insert
from .models import (TrainingSession as Session, Enrollment, TrainingEvent as Event,
    TrainingNotification as Notice, PortalUser, CourseVersion, CourseCatalog, Delegation,
    RequestRecord, RequestWorkflow, DevelopmentItem)
from . import training_policy as policy
from .time_policy import utc_now, utc_stamp, as_utc
from .utils import json_dumps, json_loads


def uid(actor):
    return getattr(actor, 'user_id', getattr(actor, 'id', None))


def manager(row, actor):
    return actor.role == 'NEEDS_ANALYST' or actor.role == row.responsible_unit


def visible_query(actor):
    enrolled = select(Enrollment.id).where(Enrollment.session_id == Session.id,
        Enrollment.user_id == uid(actor), Enrollment.status == 'ENROLLED').exists()
    return or_(Session.responsible_unit == actor.role, actor.role == 'NEEDS_ANALYST',
               Session.trainer_user_id == uid(actor), enrolled)


def visible(db, row, actor):
    return bool(db.scalar(select(Session.id).where(Session.id == row.id, visible_query(actor))))


def can_act(db, row, actor):
    person = db.get(PortalUser, uid(actor))
    effective = (getattr(actor, 'delegation', None) or {}).get('delegator_id', uid(actor))
    return bool(person and person.active and actor.role in policy.MANAGERS and
        actor.role == row.responsible_unit and (row.coordinator_id is None or row.coordinator_id == effective))


def delegated(db, row, actor, header):
    if header is None:
        return actor
    from .operations import valid_delegation
    if not str(header).isdecimal():
        raise HTTPException(403, 'Geçersiz vekâlet.')
    grant = db.get(Delegation, int(header))
    if not valid_delegation(db, grant, uid(actor)) or row.coordinator_id != grant.delegator_id:
        raise HTTPException(403, 'Bu oturum için geçerli koordinatör vekâleti yok.')
    owner = db.get(PortalUser, grant.delegator_id)
    if owner.role != row.responsible_unit:
        raise HTTPException(403, 'Vekâlet sorumlu birimi kapsamıyor.')
    return replace(actor, delegation={'id': grant.id, 'delegator_id': owner.id,
        'delegator_name': owner.display_name, 'acting_user_id': uid(actor), 'acting_user_name': actor.display_name})


def load(db, identifier, actor, header=None, expected=None):
    row = db.get(Session, identifier)
    if not row or not visible(db, row, actor):
        raise HTTPException(404, 'Eğitim oturumu bulunamadı.')
    if expected is not None:
        changed = db.execute(update(Session).where(Session.id == identifier, Session.version == expected)
            .values(version=Session.version+1, updated_at=utc_now()).execution_options(synchronize_session=False))
        if changed.rowcount != 1:
            raise HTTPException(409, 'Oturum güncellendi. Güncel kaydı açıp değişiklikleri karşılaştırın.')
        db.refresh(row)
    effective = delegated(db, row, actor, header)
    if expected is not None and not can_act(db, row, effective):
        raise HTTPException(403, 'Bu oturumun işlemi sorumlu birim/koordinatör yetkisi gerektirir.')
    return row, effective


def user_info(db, identifier):
    user = db.get(PortalUser, identifier) if identifier else None
    return {'id': user.id, 'display_name': user.display_name} if user else None


def active_user(db, identifier, role=None):
    if identifier is None:
        return
    user = db.get(PortalUser, identifier)
    if not user or not user.active or role and user.role != role:
        raise HTTPException(422, 'Aktif ve birim kapsamına uygun bir kullanıcı seçin.')


def validate_fields(db, values, actor, row=None):
    if values['responsible_unit'] not in policy.MANAGERS or values['responsible_unit'] != actor.role:
        raise HTTPException(403, 'Oturum yalnızca kendi sorumlu biriminiz için yönetilebilir.')
    if row and row.responsible_unit != values['responsible_unit']:
        raise HTTPException(422, 'Oturumun sorumlu birimi sessizce değiştirilemez.')
    active_user(db, values['coordinator_id'], values['responsible_unit'])
    active_user(db, values['trainer_user_id'])


def validate_schedule(db, row):
    if not row.start_at or not row.end_at or row.end_at <= row.start_at:
        raise HTTPException(422, 'Geçerli başlangıç ve bitiş zamanı gereklidir.')
    if not row.trainer_user_id and not row.external_trainer:
        raise HTTPException(422, 'Planlamak için eğitmen bilgisi gereklidir.')
    active_user(db, row.trainer_user_id)
    if row.delivery_mode in ('IN_PERSON','HYBRID') and not row.location:
        raise HTTPException(422, 'Bu eğitim biçimi için fiziksel konum gereklidir.')
    if row.delivery_mode in ('ONLINE','HYBRID') and not row.online_url:
        raise HTTPException(422, 'Bu eğitim biçimi için çevrim içi bağlantı gereklidir.')


def count_enrolled(db, row):
    return db.scalar(select(func.count()).select_from(Enrollment).where(
        Enrollment.session_id == row.id, Enrollment.status == 'ENROLLED'))


def delegation_options(db, row, actor):
    from .operations import valid_delegation
    return [{'id': d.id, 'delegator_name': db.get(PortalUser, d.delegator_id).display_name}
        for d in db.scalars(select(Delegation).where(Delegation.delegate_id == uid(actor),
            Delegation.delegator_id == row.coordinator_id, Delegation.active.is_(True)))
        if valid_delegation(db, d, uid(actor)) and actor.role == row.responsible_unit]


def operational_recipients(db, row):
    ids = {row.coordinator_id} if row.coordinator_id else set(db.scalars(select(PortalUser.id).where(
        PortalUser.role == row.responsible_unit, PortalUser.active.is_(True))))
    from .operations import valid_delegation
    for grant in db.scalars(select(Delegation).where(Delegation.delegator_id.in_(ids), Delegation.active.is_(True))):
        if row.coordinator_id == grant.delegator_id and valid_delegation(db, grant):
            ids.add(grant.delegate_id)
    return ids


def record_event(db, row, actor, action, before=None, details=None, recipients=()):
    info = {**(details or {}), 'delegation': getattr(actor, 'delegation', None)}
    event = Event(session_id=row.id, version=row.version, action=action,
        from_status=before or row.status, to_status=row.status, actor_id=uid(actor),
        actor_name=actor.display_name, details_json=json_dumps(info))
    db.add(event); db.flush()
    for person in set(recipients):
        user = db.get(PortalUser, person)
        if not user or not user.active:
            continue
        # Same event+recipient deduplication as the existing local notification inbox.
        db.execute(insert(Notice).values(recipient_id=person, session_id=row.id, source_event_id=event.id,
            title=policy.NOTICE_TITLES.get(action,policy.EVENTS[action]),
            message=(f'{row.title}: {next_action(db,row)}' if action in policy.NOTICE_TITLES else f'{row.title}: eğitim oturumu #{row.id}.'), created_at=utc_now())
            .on_conflict_do_nothing(index_elements=['source_event_id','recipient_id']))
    return event


def participants(db, row):
    return set(db.scalars(select(Enrollment.user_id).where(Enrollment.session_id == row.id, Enrollment.status == 'ENROLLED')))


def create(db, actor, payload):
    values = payload.model_dump(exclude={'course_version_id'})
    validate_fields(db, values, actor)
    version = db.get(CourseVersion, payload.course_version_id)
    if not version or version.state != 'PUBLISHED':
        raise HTTPException(422, 'Yeni oturum yalnızca yayımlanmış güncel ders sürümünden oluşturulabilir.')
    changed = db.execute(update(CourseCatalog).where(CourseCatalog.course_id == version.course_id,
        CourseCatalog.current_version_id == version.id).values(revision=CourseCatalog.revision))
    if changed.rowcount != 1:
        raise HTTPException(409, 'Kataloğun güncel sürümü değişti. Dersi yeniden açın.')
    db.refresh(version)
    catalog = db.get(CourseCatalog, version.course_id)
    if version.state != 'PUBLISHED':
        raise HTTPException(409, 'Dersin yayın durumu değişti.')
    if catalog.responsible_unit and catalog.responsible_unit != actor.role:
        raise HTTPException(403, 'Bu dersin sorumlu birimi için oturum açma yetkiniz yok.')
    values['title'] = values['title'] or version.title
    row = Session(course_version_id=version.id, created_by=uid(actor), **values)
    db.add(row); db.flush()
    record_event(db, row, actor, 'CREATED', details={'course_version_id': version.id})
    db.commit()
    return detail(db, row, actor)


def edit(db, row, actor, payload):
    if not policy.capabilities(row, True)['edit']:
        raise HTTPException(422, 'Bu aşamada zamanlama ve oturum bilgileri değiştirilemez.')
    values = payload.model_dump(exclude={'expected_version'})
    validate_fields(db, values, actor, row)
    values['title'] = values['title'] or db.get(CourseVersion, row.course_version_id).title
    if values['capacity'] is not None and values['capacity'] < count_enrolled(db, row):
        raise HTTPException(409, 'Kapasite mevcut katılımcı sayısının altına indirilemez.')
    changes = {k: {'before': utc_stamp(getattr(row,k)) if k.endswith('_at') else getattr(row,k),
                   'after': utc_stamp(v) if k.endswith('_at') else v}
               for k,v in values.items() if getattr(row,k) != v}
    for key, value in values.items():
        setattr(row, key, value)
    if row.status == 'SCHEDULED':
        validate_schedule(db, row)
    action = 'RESCHEDULED' if {'start_at','end_at'} & changes.keys() else 'TRAINER_CHANGED' if {'trainer_user_id','external_trainer'} & changes.keys() else 'EDIT'
    meaningful = {'start_at','end_at','trainer_user_id','external_trainer','location','online_url','delivery_mode'} & changes.keys()
    recipients = participants(db, row) if meaningful and row.status == 'SCHEDULED' else set()
    if 'coordinator_id' in changes:
        recipients |= operational_recipients(db, row)
    if not changes:
        db.rollback(); db.refresh(row)
        return detail(db, row, actor)
    record_event(db, row, actor, action, details={'changes': changes}, recipients=recipients)
    db.commit()
    return detail(db, row, actor)


def act(db, row, actor, payload):
    code, before = payload.action, row.status
    if code == 'FINALIZE_ATTENDANCE':
        if not policy.capabilities(row, True)['attendance']:
            raise HTTPException(422, 'Bu aşamada devam kesinleştirilemez.')
        if db.scalar(select(Enrollment.id).where(Enrollment.session_id == row.id,
            Enrollment.status == 'ENROLLED', Enrollment.attendance == 'UNKNOWN').limit(1)):
            raise HTTPException(422, 'Önce tüm aktif katılımcıların devam bilgisini girin.')
        if row.attendance_finalized_at:
            db.rollback(); db.refresh(row)
            return detail(db, row, actor)
        row.attendance_finalized_at = utc_now()
    else:
        rule = policy.TRANSITIONS[code]
        if before not in rule['from']:
            raise HTTPException(422, 'Oturumun mevcut aşamasında bu işlem yapılamaz.')
        if code in ('SCHEDULE','START'):
            validate_schedule(db, row)
        if code == 'CANCEL':
            if not payload.reason.strip():
                raise HTTPException(422, 'İptal gerekçesi gereklidir.')
            row.cancellation_reason = payload.reason
        if code == 'COMPLETE':
            if not row.attendance_finalized_at:
                raise HTTPException(422, 'Önce devam bilgilerini kesinleştirin.')
            if db.scalar(select(Enrollment.id).where(Enrollment.session_id == row.id,
                Enrollment.status == 'ENROLLED', Enrollment.completion == 'PENDING').limit(1)):
                raise HTTPException(422, 'Önce katılımcıların tamamlanma durumlarını girin.')
        row.status = rule['to']
    recipients = participants(db, row) if code in ('SCHEDULE','CANCEL') else operational_recipients(db, row) if code in ('START','FINALIZE_ATTENDANCE') else set()
    record_event(db, row, actor, code, before, {'reason': payload.reason}, recipients)
    db.commit()
    return detail(db, row, actor)


def enroll(db, row, actor, payload):
    if not policy.capabilities(row, True)['enroll']:
        raise HTTPException(422, 'Bu aşamada katılımcı kaydı yapılamaz.')
    active_user(db, payload.user_id)
    old = db.scalar(select(Enrollment).where(Enrollment.session_id == row.id, Enrollment.user_id == payload.user_id))
    if old and old.status == 'ENROLLED':
        raise HTTPException(409, 'Bu kullanıcı oturuma zaten kayıtlı.')
    if row.capacity is not None and count_enrolled(db, row) >= row.capacity:
        raise HTTPException(409, 'Oturum kapasitesi dolu.')
    if payload.source_request_id:
        from .operations import can_see
        user = db.get(PortalUser, uid(actor))
        flow = db.get(RequestWorkflow, payload.source_request_id)
        if not flow or flow.owner_hash != f'user:{payload.user_id}' or not can_see(db, user, payload.source_request_id):
            raise HTTPException(422, 'Kaynak talep, katılımcıya ait ve yetkiniz dahilinde olmalıdır.')
    entry = old or Enrollment(session_id=row.id, user_id=payload.user_id)
    if old:
        entry.version += 1
    entry.status = 'ENROLLED'; entry.source_request_id = payload.source_request_id
    entry.enrolled_at = utc_now(); entry.updated_at = utc_now()
    db.add(entry); db.flush()
    record_event(db, row, actor, 'ENROLLED', details={'enrollment_id': entry.id,
        'user_id': entry.user_id, 'source_request_id': entry.source_request_id}, recipients={entry.user_id})
    db.commit()
    return detail(db, row, actor)


def remove(db, row, actor, identifier, payload):
    if not policy.capabilities(row, True)['enroll']:
        raise HTTPException(422, 'Bu aşamada katılımcı kaldırılamaz.')
    changed = db.execute(update(Enrollment).where(Enrollment.id == identifier, Enrollment.session_id == row.id,
        Enrollment.version == payload.enrollment_version, Enrollment.status == 'ENROLLED')
        .values(status='REMOVED', version=Enrollment.version+1, updated_at=utc_now()))
    if changed.rowcount != 1:
        raise HTTPException(409, 'Katılımcı kaydı güncellendi veya bulunamadı.')
    entry = db.get(Enrollment, identifier)
    record_event(db, row, actor, 'REMOVED', details={'enrollment_id': identifier}, recipients={entry.user_id})
    db.commit()
    return detail(db, row, actor)


def results(db, row, actor, payload, kind):
    if not policy.capabilities(row, True)[kind]:
        raise HTTPException(422, 'Devam/tamamlanma yalnızca başlayan veya tamamlanan oturumlarda kaydedilebilir.')
    changes = []
    for value in payload.rows:
        other = 'completion' if kind == 'attendance' else 'attendance'
        if getattr(value, kind) is None or getattr(value, other) is not None:
            raise HTTPException(422, 'Devam ve tamamlanma ayrı işlemlerle kaydedilmelidir.')
        entry = db.get(Enrollment, value.id)
        if not entry or entry.session_id != row.id or entry.status != 'ENROLLED':
            raise HTTPException(422, 'Oturuma kayıtlı aktif katılımcı bulunamadı.')
        if entry.version != value.version:
            raise HTTPException(409, 'Katılımcı sonucu güncellendi. Güncel kayıtla karşılaştırın.')
        new = getattr(value, kind); before = getattr(entry, kind)
        if new == before:
            continue
        update_values = {kind: new, 'version': Enrollment.version+1, 'updated_at': utc_now()}
        if kind == 'completion':
            update_values['completed_at'] = utc_now() if new == 'COMPLETED' else None
        changed = db.execute(update(Enrollment).where(Enrollment.id == value.id, Enrollment.version == value.version).values(**update_values))
        if changed.rowcount != 1:
            raise HTTPException(409, 'Katılımcı sonucu aynı anda güncellendi.')
        changes.append({'enrollment_id': value.id, 'before': before, 'after': new})
    if not changes:
        db.rollback(); db.refresh(row)
        return detail(db, row, actor)
    if kind == 'attendance':
        row.attendance_finalized_at = None
    record_event(db, row, actor, kind.upper(), details={'changes': changes})
    if kind == "completion":
        from .evaluation import on_completion
        for change in changes:
            if change["after"] == "COMPLETED":
                on_completion(db, db.get(Enrollment, change["enrollment_id"]), actor)
    # Intentionally never mutate RequestWorkflow or a human decision here.
    db.commit()
    return detail(db, row, actor)


def next_action(db, row):
    if row.status == 'DRAFT': return 'Oturum bilgilerini tamamlayıp planlayın'
    if row.status == 'SCHEDULED': return 'Eğitim başladığında oturumu başlatın'
    if row.status in ('IN_PROGRESS','COMPLETED'):
        if not row.attendance_finalized_at: return 'Devam bilgilerini girip kesinleştirin'
        if db.scalar(select(Enrollment.id).where(Enrollment.session_id == row.id,
            Enrollment.status == 'ENROLLED', Enrollment.completion == 'PENDING').limit(1)):
            return 'Katılımcıların tamamlanma durumlarını girin'
        if row.status == 'IN_PROGRESS': return 'Oturumu tamamlayın'
    return 'Bekleyen işlem yok'


def summary(db, row):
    version = db.get(CourseVersion, row.course_version_id)
    return {'id': row.id, 'title': row.title, 'course_id': version.course_id,
        'course_title': version.title, 'course_version_id': version.id, 'course_version_number': version.version_number,
        'responsible_unit': row.responsible_unit, 'responsible_unit_label': policy.ROLES[row.responsible_unit],
        'coordinator': user_info(db, row.coordinator_id), 'trainer': user_info(db, row.trainer_user_id),
        'external_trainer': row.external_trainer, 'status': row.status, 'status_label': policy.STATES[row.status],
        'start_at': utc_stamp(row.start_at), 'end_at': utc_stamp(row.end_at), 'capacity': row.capacity,
        'participant_count': count_enrolled(db, row), 'delivery_mode': row.delivery_mode,
        'delivery_label': policy.MODES[row.delivery_mode], 'version': row.version,
        'updated_at': utc_stamp(row.updated_at), 'next_action': next_action(db, row)}


def trace(db, row, actor):
    from .operations import can_see
    version = db.get(CourseVersion, row.course_version_id)
    user = db.get(PortalUser, uid(actor))
    result = {'course_version_id': version.id, 'course_id': version.course_id, 'version_number': version.version_number}
    if version.source_request_id and can_see(db, user, version.source_request_id):
        result.update(request_id=version.source_request_id, decision_id=version.source_decision_id,
                      analysis_id=version.source_analysis_id)
        from .development import visible as development_visible
        item = db.get(DevelopmentItem, version.source_development_id)
        if item and development_visible(db, item, actor):
            result['development_id'] = item.id
    return result


def detail(db, row, actor):
    from .operations import can_see
    managed = manager(row, actor)
    authorized = can_act(db, row, actor)
    query = select(Enrollment).where(Enrollment.session_id == row.id).order_by(Enrollment.id)
    if not managed: query = query.where(Enrollment.user_id == uid(actor))
    user = db.get(PortalUser, uid(actor))
    entries = [{'id': e.id, 'user': user_info(db, e.user_id), 'status': e.status, 'version': e.version,
        'attendance': e.attendance, 'completion': e.completion, 'enrolled_at': utc_stamp(e.enrolled_at),
        'completed_at': utc_stamp(e.completed_at),
        'source_request_id': e.source_request_id if e.source_request_id and can_see(db,user,e.source_request_id) else None}
        for e in db.scalars(query)]
    history_query = select(Event).where(Event.session_id == row.id).order_by(Event.id)
    if not managed: history_query = history_query.where(Event.action.in_(('CREATED','SCHEDULE','START','COMPLETE','CANCEL','RESCHEDULED')))
    from .evaluation import aggregate
    reviewers=[user_info(db,u.id) for u in db.scalars(select(PortalUser).where(PortalUser.active.is_(True),PortalUser.role.in_(('NEEDS_ANALYST',row.responsible_unit))))] if authorized else []
    return {'can_plan_evaluation': authorized, 'evaluation_reviewers': reviewers, 'effectiveness': aggregate(db,actor,session_id=row.id) if managed else None, **summary(db,row), 'location': row.location, 'online_url': row.online_url,
        'created_by': user_info(db, row.created_by), 'created_at': utc_stamp(row.created_at),
        'cancellation_reason': row.cancellation_reason, 'attendance_finalized_at': utc_stamp(row.attendance_finalized_at),
        'capabilities': policy.capabilities(row, authorized), 'actions': policy.actions(row, authorized),
        'acting_delegation': getattr(actor, 'delegation', None), 'delegations': delegation_options(db,row,actor),
        'enrollments': entries, 'trace': trace(db,row,actor),
        'history': [{'id': e.id, 'action': e.action, 'label': policy.EVENTS[e.action], 'actor': e.actor_name,
            'at': utc_stamp(e.created_at), 'from_status': policy.STATES[e.from_status], 'to_status': policy.STATES[e.to_status],
            'details': json_loads(e.details_json,{}) if managed else {}}
            for e in db.scalars(history_query)]}


def queue(db, actor, status, day, search, offset, limit):
    query = select(Session).join(CourseVersion, CourseVersion.id == Session.course_version_id).where(visible_query(actor))
    if status: query = query.where(Session.status == status)
    if day:
        # The date filter is a Turkish calendar day, not an implicit UTC day.
        from .time_policy import training_day_bounds
        start, end = training_day_bounds(day)
        query = query.where(Session.start_at >= start, Session.start_at < end)
    if search: query = query.where(or_(Session.title.icontains(search,autoescape=True), CourseVersion.title.icontains(search,autoescape=True)))
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    rows = db.scalars(query.order_by(Session.start_at.is_(None), Session.start_at, Session.id).offset(offset).limit(limit))
    return {'items': [summary(db,r) for r in rows], 'total': total, 'offset': offset, 'limit': limit}


def options(db, actor, course_version_id=None, session_id=None, header=None):
    row = None
    if session_id:
        row, actor = load(db,session_id,actor,header)
        if not can_act(db,row,actor): raise HTTPException(403,'Katılımcı seçenekleri için operasyon yetkisi gereklidir.')
    if actor.role not in policy.MANAGERS: raise HTTPException(403,'Eğitim operasyon yetkisi gereklidir.')
    if course_version_id:
        version = db.get(CourseVersion,course_version_id)
        catalog = db.get(CourseCatalog,version.course_id) if version else None
        if not version or version.state != 'PUBLISHED' or not catalog or catalog.current_version_id != version.id:
            raise HTTPException(422,'Güncel yayımlanmış ders sürümü seçin.')
        if catalog.responsible_unit and catalog.responsible_unit != actor.role:
            raise HTTPException(403,'Bu dersin sorumlu birimi için oturum açılamaz.')
    users = [user_info(db,u.id) for u in db.scalars(select(PortalUser).where(PortalUser.active.is_(True)).order_by(PortalUser.display_name))]
    coordinators = [u for u in users if db.get(PortalUser,u['id']).role == actor.role]
    from .workflow import audience_scope
    requests = [{'id':r.id,'title':r.topic or f'Talep #{r.id}','user_id':int(f.owner_hash[5:])}
        for r,f in db.execute(select(RequestRecord,RequestWorkflow).join(RequestWorkflow).where(
            audience_scope(actor.token_hash,True,actor.role)))
        if f.owner_hash.startswith('user:') and f.owner_hash[5:].isdecimal()]
    return {'units': [{'code':actor.role,'label':policy.ROLES[actor.role]}], 'users':users,
        'source_requests': requests,
        'coordinators':coordinators, 'modes':policy.MODES, 'attendance':policy.ATTENDANCE, 'completion':policy.COMPLETION,
        'states':policy.STATES}


def catalog_action(db, version, actor):
    catalog = db.get(CourseCatalog,version.course_id) if version.course_id else None
    return bool(actor.role in policy.MANAGERS and version.state == 'PUBLISHED' and catalog and
        catalog.current_version_id == version.id and catalog.responsible_unit in (None,actor.role))


def request_links(db, record, flow, role):
    # Called only after the existing request authorization has succeeded.
    rows = db.execute(select(Enrollment,Session,CourseVersion).join(Session,Session.id==Enrollment.session_id)
        .join(CourseVersion,CourseVersion.id==Session.course_version_id).where(Enrollment.source_request_id==record.id)).all()
    return [{'session_id':s.id,'title':s.title,'course_version_number':v.version_number,
        'user':user_info(db,e.user_id),'attendance':policy.ATTENDANCE[e.attendance],
        'completion':policy.COMPLETION[e.completion], 'training_completed':e.completion=='COMPLETED',
        'enrollment_status':e.status,'session_status':policy.STATES[s.status],
        'can_open':role in ('NEEDS_ANALYST',s.responsible_unit) or bool(flow and flow.owner_hash==f'user:{e.user_id}')}
        for e,s,v in rows]


def inbox_items(db, actor, identifiers=None):
    rows = db.scalars(select(Session).where(visible_query(actor), Session.status != 'CANCELLED').where(Session.id.in_(identifiers)) if identifiers is not None else select(Session).where(visible_query(actor), Session.status != 'CANCELLED'))
    result=[]
    for row in rows:
        next_label=next_action(db,row)
        if next_label=='Bekleyen işlem yok': continue
        actors=[actor]+[delegated(db,row,actor,d['id']) for d in delegation_options(db,row,actor)]
        for effective in actors:
            if not can_act(db,row,effective):continue
            result.append({'kind':'training','session_id':row.id,'request_id':0,'title':row.title,
                'state':row.status,'state_label':policy.STATES[row.status], 'status':row.status,
                'work_type_label':'Eğitim oturumu','responsible_unit_label':policy.ROLES[row.responsible_unit],
                'assignee':user_info(db,row.coordinator_id),'updated_at':utc_stamp(row.updated_at),
                'aging':{'current_stage_seconds':max(0,int((utc_now()-as_utc(row.updated_at)).total_seconds()))},
                'action_required':next_label,'delegation':getattr(effective,'delegation',None)})
    return result


def notification_payload(db, note, actor):
    row=db.get(Session,note.session_id)
    accessible=bool(row and visible(db,row,actor))
    grants=delegation_options(db,row,actor) if accessible else []
    return {'id':-note.id,'title':note.title if accessible else 'Eğitim erişiminiz değişti',
        'message':note.message if accessible else 'Bu oturuma güncel erişiminiz bulunmuyor.',
        'session_id':row.id if accessible else None,'request_id':None,
        'delegation_id':grants[0]['id'] if grants else None,'created_at':utc_stamp(note.created_at),
        'read_at':utc_stamp(note.read_at),'importance':'normal'}
