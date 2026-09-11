"""Deterministic, evidence-first explanations. No scores or expiry policy."""
from sqlalchemy import select, func, or_, and_
from .position_models import PositionProfile as Profile, PositionRevision as Revision, PositionRequirement as Requirement, UserPosition
from .skill_models import SkillEvidence as Evidence, RequestSkillNeed as Need, CourseSkillMapping as Mapping
from .models import Enrollment, LearningEvaluation, RequestWorkflow, CourseVersion, PortalUser
from .governance_models import CourseGovernance
from .time_policy import utc_stamp, utc_now
from . import positions, position_policy as policy, skill_evidence, skill_reporting

def current_sources():
    needs = select(Need.id).where(Need.active.is_(True), Need.human_verified.is_(True))
    completions = select(Enrollment.id).where(Enrollment.status == 'ENROLLED', Enrollment.completion == 'COMPLETED', Enrollment.completed_at == Evidence.observed_at)
    evaluations = select(LearningEvaluation.id).join(Enrollment, Enrollment.id == LearningEvaluation.enrollment_id).where(
        Enrollment.status == 'ENROLLED', Enrollment.completion == 'COMPLETED', LearningEvaluation.completion_at == Enrollment.completed_at)
    return or_(Evidence.request_need_id.in_(needs),
        and_(Evidence.evidence_type == 'TRAINING_COMPLETION', Evidence.enrollment_id.in_(completions)),
        Evidence.evaluation_id.in_(evaluations))

def courses(db, skill_id):
    return [{'id': r.id, 'title': r.title, 'version_number': r.version_number}
        for r in db.scalars(select(CourseVersion).outerjoin(CourseGovernance, CourseGovernance.course_id == CourseVersion.course_id).where(
            CourseVersion.state == 'PUBLISHED', CourseVersion.id.in_(select(Mapping.course_version_id).where(Mapping.skill_id == skill_id)),
            or_(CourseGovernance.lifecycle_state.is_(None), CourseGovernance.lifecycle_state == 'ACTIVE')).order_by(CourseVersion.title))]

def evidence_state(db, user_id, skill_id):
    query = select(Evidence).where(Evidence.user_id == user_id, Evidence.skill_id == skill_id)
    total, last = db.execute(select(func.count(), func.max(Evidence.observed_at)).where(Evidence.user_id == user_id, Evidence.skill_id == skill_id)).one()
    types = [{'type': kind, 'label': skill_evidence.LABELS[kind], 'count': count}
        for kind, count in db.execute(select(Evidence.evidence_type, func.count()).where(
            Evidence.user_id == user_id, Evidence.skill_id == skill_id, current_sources()).group_by(Evidence.evidence_type))]
    by_type = {r['type']: r['count'] for r in types}
    needs = db.scalar(select(func.count()).select_from(Need).join(RequestWorkflow, RequestWorkflow.request_id == Need.request_id).where(
        Need.skill_id == skill_id, Need.active.is_(True), Need.human_verified.is_(True),
        RequestWorkflow.owner_hash == f'user:{user_id}', RequestWorkflow.status != 'RESOLVED'))
    unmet = db.scalar(select(func.count(func.distinct(Evidence.evaluation_id))).where(Evidence.user_id == user_id,
        Evidence.skill_id == skill_id, Evidence.signal.in_(('PARTIALLY_RESOLVED','NOT_RESOLVED')), current_sources()))
    state = 'NO_EVIDENCE' if not total else 'EVIDENCE_PRESENT'
    if by_type.get('TRAINING_COMPLETION') or by_type.get('SELF_EVALUATION'): state = 'DEVELOPMENT_EVIDENCE'
    if by_type.get('OUTCOME_EVALUATION') or by_type.get('AUTHORIZED_VALIDATION'): state = 'OUTCOME_EVIDENCE'
    reasons = [f"{r['label']}: {r['count']} kayıt" for r in types]
    if not total: reasons.append('Bu yetkinlik için sistemde henüz kanıt bulunmuyor. Bu, yetkinliğin bilinmediği anlamına gelmez.')
    elif not types: reasons.append('Yalnızca geçmiş kanıtlar var; kaynakların güncel durumu değişmiş. Kayıtlar korunuyor.')
    if not (by_type.get('OUTCOME_EVALUATION') or by_type.get('AUTHORIZED_VALIDATION')): reasons.append('İlgili ihtiyacın sonucuna ilişkin güncel değerlendirme henüz yok.')
    reasons.append(f'{needs} açık talepte doğrulanmış ihtiyaç var.' if needs else 'Açık ve doğrulanmış yetkinlik ihtiyacı kaydı yok.')
    if unmet: reasons.append(f'{unmet} sonuç değerlendirmesinde ihtiyaç kısmen karşılandı veya karşılanmadı.')
    return {'state': state, 'state_label': policy.STATES[state], 'evidence_count': total, 'current_evidence_count': sum(by_type.values()),
        'evidence_types': types, 'last_evidence_at': utc_stamp(last), 'open_need_count': needs, 'unmet_outcome_count': unmet,
        'development_signal': bool(needs or unmet), 'explanation': reasons,
        'completed_training': bool(by_type.get('TRAINING_COMPLETION')), 'self_evaluation': bool(by_type.get('SELF_EVALUATION')),
        'participant_outcome': bool(by_type.get('OUTCOME_EVALUATION')), 'authorized_outcome': bool(by_type.get('AUTHORIZED_VALIDATION'))}

def mine(db, actor):
    link = db.get(UserPosition, actor.user_id)
    if not link or not link.profile_id: return {'assigned': False, 'message': 'Hesabınıza bir pozisyon profili tanımlanmamış.'}
    profile = positions.get_profile(db, link.profile_id); rev = positions.revision(db, profile)
    rows = []
    for req in positions.requirements(db, rev):
        state = evidence_state(db, actor.user_id, req.skill_id)
        rows.append({**positions.requirement_data(req), **state, 'courses': courses(db, req.skill_id),
            'can_request': actor.role == 'EMPLOYEE' and profile.status == 'ACTIVE'})
    required = [r for r in rows if r['requirement_type'] == 'REQUIRED']
    return {'assigned': True, 'profile': positions.brief(profile), 'requirement_version': rev.version,
        'calculated_at': utc_stamp(utc_now()), 'requirements': rows,
        'summary': {'required': len(required), 'with_evidence': sum(bool(r['evidence_count']) for r in required),
            'without_evidence': sum(not r['evidence_count'] for r in required), 'open_signals': sum(r['development_signal'] for r in required)},
        'meaning': 'Sistemdeki kayıtların kapsamıdır; yeterlilik, performans veya role uygunluk değerlendirmesi değildir. Kanıtlara süre aşımı uygulanmaz.'}

def aggregate(db, actor, profile_id):
    policy.require_manager(actor)
    profile = positions.get_profile(db, profile_id); rev = positions.revision(db, profile)
    users = select(UserPosition.user_id).join(PortalUser, PortalUser.id == UserPosition.user_id).where(UserPosition.profile_id == profile_id, PortalUser.active.is_(True))
    count = db.scalar(select(func.count()).select_from(users.subquery()))
    disclosed = count >= policy.MIN_AGGREGATE_USERS
    items = []
    for req in positions.requirements(db, rev):
        evidence_users = select(Evidence.user_id).where(Evidence.skill_id == req.skill_id, Evidence.user_id.in_(users)).distinct()
        needs_users = select(Need.request_id).join(RequestWorkflow, RequestWorkflow.request_id == Need.request_id).where(
            Need.skill_id == req.skill_id, Need.active.is_(True), Need.human_verified.is_(True), RequestWorkflow.status != 'RESOLVED',
            RequestWorkflow.owner_hash.in_(select(func.printf('user:%d', UserPosition.user_id)).where(UserPosition.profile_id == profile_id)))
        covered = db.scalar(select(func.count()).select_from(evidence_users.subquery())) if disclosed else None
        open_count = db.scalar(select(func.count()).select_from(needs_users.subquery())) if disclosed else None
        need_people = db.scalar(select(func.count()).select_from(needs_users.with_only_columns(RequestWorkflow.owner_hash).distinct().subquery())) if disclosed else 0
        # Complementary suppression: even a large group must not reveal a one-person cell.
        safe_covered = covered if covered is not None and covered >= policy.MIN_AGGREGATE_USERS and count-covered >= policy.MIN_AGGREGATE_USERS else None
        safe_open = open_count if disclosed and need_people >= policy.MIN_AGGREGATE_USERS and count-need_people >= policy.MIN_AGGREGATE_USERS else None
        items.append({**positions.requirement_data(req), 'users_with_evidence': safe_covered,
            'open_need_count': safe_open, 'courses': courses(db, req.skill_id)})
    return {'profile': positions.brief(profile), 'requirement_version': rev.version,
        'assigned_user_count': count if disclosed else None, 'suppressed': not disclosed,
        'privacy_note': 'Kişi kaynaklı sayılar küçük gruplarda ve küçük hücrelerde gizlenir. Bireysel karşılaştırma yapılmaz.', 'requirements': items}

def planned_count(db, skill_id):
    return db.scalar(select(func.count(func.distinct(Profile.id))).join(Revision, Revision.profile_id == Profile.id)
        .join(Requirement, Requirement.revision_id == Revision.id).where(Profile.status == 'ACTIVE', Revision.sealed.is_(True),
            Revision.version == Profile.version, Requirement.skill_id == skill_id, Requirement.requirement_type == 'REQUIRED'))

def planning(db, actor, search, offset, limit):
    policy.require_manager(actor)
    data = skill_reporting.catalog(db, actor, search, offset, limit)
    for row in data['items']:
        row['planned_profiles'] = planned_count(db, row['id'])
        row['planning_signal'] = bool(row['planned_profiles'] and row['active_demand'] and not row['published_version_count'])
    data['meaning'] = 'Planlanan ihtiyaç pozisyon gereksinimidir; gözlenen ihtiyaç gerçek taleptir. Sayılar birbirine eklenmez.'
    return data
