"""Versioned position management; no authentication-role or workflow mutations."""
from fastapi import HTTPException
from sqlalchemy import select, update, func, or_
from sqlalchemy.exc import IntegrityError
from .position_models import PositionProfile as Profile, PositionRevision as Revision, PositionRequirement as Requirement, UserPosition, PositionAudit, RequestPositionSource
from .models import PortalUser, UserOrganization
from .skills import normalize, get_skill
from .utils import json_dumps, json_loads
from .time_policy import utc_now, utc_stamp
from . import position_policy as policy

def get_profile(db, identifier):
    row = db.get(Profile, identifier)
    if not row: raise HTTPException(404, 'Pozisyon profili bulunamadı.')
    return row

def brief(row):
    return {key: getattr(row, key) for key in ('id','name','code','description','organization','unit','status','version')}

def revision(db, profile, number=None):
    row = db.scalar(select(Revision).where(Revision.profile_id == profile.id, Revision.version == (number or profile.version), Revision.sealed.is_(True)))
    if not row: raise HTTPException(404, 'Gereksinim sürümü bulunamadı.')
    return row

def requirement_data(row):
    return {'id': row.id, 'skill_id': row.skill_id, 'skill': row.skill_name,
            'requirement_type': row.requirement_type, 'type_label': policy.TYPES[row.requirement_type], 'rationale': row.rationale}

def requirements(db, rev):
    return list(db.scalars(select(Requirement).where(Requirement.revision_id == rev.id).order_by(Requirement.id)))

def audit(db, actor, action, profile_id=None, user_id=None, **details):
    db.add(PositionAudit(profile_id=profile_id, user_id=user_id, actor_id=actor.user_id,
        actor_name=actor.display_name, action=action, details_json=json_dumps(details)))

def write(db, actor, payload, identifier=None):
    policy.require_manager(actor)
    identifiers = [r.skill_id for r in payload.requirements]
    if len(set(identifiers)) != len(identifiers): raise HTTPException(422, 'Aynı yetkinlik bir profilde bir kez yer alabilir.')
    try:
        row = get_profile(db, identifier) if identifier else None
        old = brief(row) if row else None
        retained = {r.skill_id: (r.requirement_type, r.rationale) for r in requirements(db, revision(db, row))} if row else {}
        if row:
            changed = db.execute(update(Profile).where(Profile.id == row.id, Profile.version == payload.expected_version)
                .values(version=Profile.version + 1, updated_at=utc_now()))
            if changed.rowcount != 1: raise HTTPException(409, 'Profil değişti; güncel sürümü inceleyin. Taslağınızı koruyun.')
            db.refresh(row)
        else:
            row = Profile(name=payload.name, normalized_name=normalize(payload.name), created_by=actor.user_id)
            db.add(row); db.flush()
        for field in ('name','description','organization','unit','status'):
            setattr(row, field, getattr(payload, field) or ('' if field == 'description' else None))
        row.code = normalize(payload.code).upper() if payload.code else None
        row.normalized_name = normalize(payload.name)
        entries = []
        for item in payload.requirements:
            skill = get_skill(db, item.skill_id)
            if skill.status != 'ACTIVE' and retained.get(skill.id) != (item.requirement_type, item.rationale):
                raise HTTPException(422, 'Yeni veya değiştirilen gereksinim için aktif yetkinlik seçin.')
            db.execute(update(type(skill)).where(type(skill).id == skill.id).values(version=type(skill).version))
            entries.append({'skill_id': skill.id, 'skill_name': skill.canonical_name, 'requirement_type': item.requirement_type, 'rationale': item.rationale})
        db.flush()
        rev = Revision(profile_id=row.id, version=row.version, snapshot_json=json_dumps({**brief(row), 'requirements': entries}), created_by=actor.user_id)
        db.add(rev); db.flush()
        for entry in entries: db.add(Requirement(revision_id=rev.id, created_by=actor.user_id, **entry))
        db.flush(); rev.sealed = True; db.flush()
        audit(db, actor, 'PROFILE_UPDATED' if identifier else 'PROFILE_CREATED', row.id, before=old, version=row.version)
        db.commit(); return detail(db, actor, row.id)
    except IntegrityError:
        db.rollback(); raise HTTPException(409, 'Profil adı/kodu kullanılıyor veya kayıt eşzamanlı değişti.')

def catalog(db, actor, search, offset, limit):
    policy.require_manager(actor)
    query = select(Profile)
    if search: query = query.where(or_(Profile.normalized_name.contains(normalize(search), autoescape=True), Profile.code.icontains(search, autoescape=True)))
    return {'items': [brief(r) for r in db.scalars(query.order_by(Profile.normalized_name).offset(offset).limit(limit))],
        'total': db.scalar(select(func.count()).select_from(query.subquery())), 'offset': offset, 'limit': limit}

def detail(db, actor, identifier, version=None):
    policy.require_manager(actor)
    row = get_profile(db, identifier); rev = revision(db, row, version)
    return {**json_loads(rev.snapshot_json, {}), 'requirements': [requirement_data(r) for r in requirements(db, rev)],
        'current_version': row.version, 'can_edit': rev.version == row.version,
        'history': [{'version': r.version, 'at': utc_stamp(r.created_at), 'actor': db.get(PortalUser, r.created_by).display_name}
            for r in db.scalars(select(Revision).where(Revision.profile_id == row.id, Revision.sealed.is_(True)).order_by(Revision.version.desc()))]}

def association(db, user_id):
    link = db.get(UserPosition, user_id)
    return {'profile_id': link.profile_id if link else None, 'version': link.version if link else 0}

def context(db, actor):
    link = association(db, actor.user_id) if actor else {'profile_id': None}
    return {'has_position': bool(link['profile_id']), 'can_manage_positions': policy.can_manage(actor)}

def users(db, actor, search, offset, limit):
    policy.require_manager(actor)
    query = select(PortalUser).where(PortalUser.active.is_(True))
    if search: query = query.where(or_(PortalUser.username.icontains(search, autoescape=True), PortalUser.display_name.icontains(search, autoescape=True)))
    rows = []
    for person in db.scalars(query.order_by(PortalUser.username).offset(offset).limit(limit)):
        link = association(db, person.id); org = db.get(UserOrganization, person.id)
        profile = db.get(Profile, link['profile_id']) if link['profile_id'] else None
        rows.append({'id': person.id, 'username': person.username, 'display_name': person.display_name,
            'organization': org.organization if org else None, 'unit': org.unit if org else None,
            **link, 'profile_name': profile.name if profile else None})
    return {'items': rows, 'total': db.scalar(select(func.count()).select_from(query.subquery())), 'offset': offset, 'limit': limit}

def assign(db, actor, user_id, payload):
    policy.require_manager(actor)
    user = db.get(PortalUser, user_id)
    if not user or not user.active: raise HTTPException(404, 'Aktif kullanıcı bulunamadı.')
    try:
        if payload.profile_id:
            profile = get_profile(db, payload.profile_id)
            db.execute(update(Profile).where(Profile.id == profile.id).values(version=Profile.version)); db.refresh(profile)
            if profile.status != 'ACTIVE': raise HTTPException(422, 'Pasif profil yeni kullanıcıya atanamaz.')
        link = db.get(UserPosition, user_id); before = association(db, user_id)
        if link:
            changed = db.execute(update(UserPosition).where(UserPosition.user_id == user_id, UserPosition.version == payload.expected_version)
                .values(profile_id=payload.profile_id, version=UserPosition.version + 1, assigned_by=actor.user_id, updated_at=utc_now()))
            if changed.rowcount != 1: raise HTTPException(409, 'Kullanıcının pozisyon ilişkisi değişti; güncel kaydı açın.')
        else:
            if payload.expected_version != 0: raise HTTPException(409, 'Pozisyon ilişkisi sürümü güncel değil.')
            db.add(UserPosition(user_id=user_id, profile_id=payload.profile_id, assigned_by=actor.user_id))
        db.flush(); audit(db, actor, 'POSITION_ASSIGNED' if payload.profile_id else 'POSITION_UNASSIGNED', payload.profile_id,
            user_id=user_id, before=before, after=association(db, user_id))
        db.commit()
        # Position changes create a new requirement snapshot lazily from the
        # active policies.  Historical requirements are never deleted.
        try:
            from . import governance
            governance.sync_requirements(db, user_id)
        except Exception:
            db.rollback()
        return association(db, user_id)
    except IntegrityError:
        db.rollback(); raise HTTPException(409, 'Pozisyon ilişkisi başka bir işlemde değişti.')

def source_for_requirement(db, actor, requirement_id):
    if actor.role != 'EMPLOYEE': raise HTTPException(403, 'İhtiyaç oluşturma çalışan hesabına aittir.')
    # Serialize assignment/profile changes with final explicit request submission.
    db.execute(update(UserPosition).where(UserPosition.user_id == actor.user_id).values(version=UserPosition.version))
    link = db.get(UserPosition, actor.user_id)
    req = db.get(Requirement, requirement_id)
    rev = db.get(Revision, req.revision_id) if req else None
    if not link or not rev or link.profile_id != rev.profile_id: raise HTTPException(404, 'Kendi pozisyonunuzda bu gereksinim bulunamadı.')
    profile = get_profile(db, rev.profile_id)
    if not rev.sealed or rev.version != profile.version or profile.status != 'ACTIVE':
        raise HTTPException(409, 'Pozisyon gereksinimleri değişti. Metninizi koruyup güncel gereksinimi seçin.')
    return {'position_profile_id': profile.id, 'position_version': rev.version, 'position_name': profile.name,
        'requirement_id': req.id, 'skill_id': req.skill_id, 'skill': req.skill_name,
        'requirement_type': req.requirement_type, 'rationale': req.rationale}

def request_source(db, request_id):
    row = db.get(RequestPositionSource, request_id)
    return json_loads(row.source_json, {}) if row else None

def validate_retry_source(db, request_id, requirement_id):
    row = db.get(RequestPositionSource, request_id)
    if (row.requirement_id if row else None) != requirement_id:
        raise HTTPException(409, 'Bu gönderim anahtarı farklı bir gereksinim kaynağına bağlı.')

def record_source(db, actor, request_id, requirement_id):
    data = source_for_requirement(db, actor, requirement_id)
    db.add(RequestPositionSource(request_id=request_id, requirement_id=requirement_id, user_id=actor.user_id, source_json=json_dumps(data)))
    return data
