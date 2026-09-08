"""Demand/coverage counts, scoped to the existing request and training authority."""
from sqlalchemy import select,func,and_,or_
from .skill_models import Skill,RequestSkillNeed as Need,CourseSkillMapping as Mapping,SkillEvidence as Evidence
from .models import RequestRecord,RequestWorkflow,RequestReferral,CourseVersion,LearningEvaluation,Enrollment,TrainingSession
from . import skills,skill_evidence


def request_scope(actor):
    if actor.role=='NEEDS_ANALYST':return True
    return Need.request_id.in_(select(RequestReferral.request_id).where(RequestReferral.department==actor.role,
        RequestReferral.active.is_(True),RequestReferral.training_need_confirmed.is_(True)))


def summary(db,skill,actor):
    needs=select(Need).where(Need.skill_id==skill.id,Need.active.is_(True),request_scope(actor))
    rows=needs.subquery()
    confirmed=db.scalar(select(func.count()).select_from(rows).where(rows.c.human_verified.is_(True)))
    suggested=db.scalar(select(func.count()).select_from(rows).where(rows.c.human_verified.is_(False)))
    active=db.scalar(select(func.count()).select_from(rows).outerjoin(RequestWorkflow,RequestWorkflow.request_id==rows.c.request_id)
        .where(rows.c.human_verified.is_(True),or_(RequestWorkflow.status!='RESOLVED',RequestWorkflow.request_id.is_(None))))
    courses=db.scalar(select(func.count(func.distinct(Mapping.course_version_id))).join(CourseVersion,CourseVersion.id==Mapping.course_version_id)
        .where(Mapping.skill_id==skill.id,CourseVersion.state=='PUBLISHED'))
    evidence_count=db.scalar(select(func.count()).select_from(Evidence).where(Evidence.skill_id==skill.id,skill_evidence.visible_aggregate(actor)))
    # Count actual evaluations once per skill, never once per outcome mapping.
    outcome_ids=select(Evidence.evaluation_id).where(Evidence.skill_id==skill.id,skill_evidence.visible_aggregate(actor),
        Evidence.evidence_type.in_(('OUTCOME_EVALUATION','AUTHORIZED_VALIDATION')))
    outcomes=[{'source':source,'outcome':outcome,'count':count} for source,outcome,count in db.execute(
        select(LearningEvaluation.evaluator_source,LearningEvaluation.outcome,func.count()).join(Enrollment,Enrollment.id==LearningEvaluation.enrollment_id)
        .where(LearningEvaluation.id.in_(outcome_ids),Enrollment.status=='ENROLLED',Enrollment.completion=='COMPLETED',
            LearningEvaluation.completion_at==Enrollment.completed_at)
        .group_by(LearningEvaluation.evaluator_source,LearningEvaluation.outcome))]
    signals=[]
    if active and not courses:signals.append({'kind':'NO_CATALOG_COVERAGE','count':active,'text':'Açık ihtiyaç var; eşleştirilmiş yayımlanmış ders yok'})
    if active>1:signals.append({'kind':'REPEATED_DEMAND','count':active,'text':'Birden fazla açık talepte aynı yetkinlik ihtiyacı'})
    for source in ('PARTICIPANT','AUTHORIZED_REVIEWER'):
        low=sum(r['count'] for r in outcomes if r['source']==source and r['outcome'] in ('PARTIALLY_RESOLVED','NOT_RESOLVED'))
        if low:signals.append({'kind':'UNMET_OUTCOME','count':low,'source':source,'text':'İlişkili ihtiyaç kısmen / karşılanmadı'})
    return {'confirmed_demand':confirmed,'ai_suggested':suggested,'active_demand':active,'closed_request_count':confirmed-active,
        'published_version_count':courses,'evidence_count':evidence_count,'outcomes':outcomes,'signals':signals}


def catalog(db,actor,search,offset,limit):
    skills.require_manager(actor);query=skills.search_query(search)
    items=[{**skills.skill_data(db,row),**summary(db,row,actor)} for row in db.scalars(query.order_by(Skill.normalized_name).offset(offset).limit(limit))]
    return {'items':items,'total':db.scalar(select(func.count()).select_from(query.subquery())),'offset':offset,'limit':limit,'can_manage':actor.role=='NEEDS_ANALYST'}


def detail(db,actor,skill_id):
    skills.require_manager(actor);skill=skills.get_skill(db,skill_id)
    versions=db.scalars(select(CourseVersion).where(CourseVersion.id.in_(select(Mapping.course_version_id).where(Mapping.skill_id==skill_id)),CourseVersion.state=='PUBLISHED').order_by(CourseVersion.title))
    coverage=[{'id':v.id,'title':v.title,'version_number':v.version_number,'mappings':[m for m in skills.mappings(db,v) if m['skill_id']==skill_id]} for v in versions]
    needs=db.execute(select(Need,RequestRecord.topic,RequestWorkflow.status).join(RequestRecord,RequestRecord.id==Need.request_id)
        .outerjoin(RequestWorkflow,RequestWorkflow.request_id==Need.request_id).where(Need.skill_id==skill_id,request_scope(actor)).order_by(Need.id.desc()).limit(30))
    # The detailed links obey the same scope as normal request lists. No user roster.
    from .evaluation import aggregate
    related_versions=select(Mapping.course_version_id).where(Mapping.skill_id==skill_id)
    version_ids=set(db.scalars(related_versions));improvements=[]
    evaluation_versions=[row for version_id in sorted(version_ids)
        for row in aggregate(db,actor,course_version_id=version_id)['versions']]
    for version in evaluation_versions:
        if version['course_version_id'] not in version_ids:continue
        mapped_text={m.outcome_text for m in db.scalars(select(Mapping).where(Mapping.skill_id==skill_id,Mapping.course_version_id==version['course_version_id'])) if m.outcome_index>=0}
        for signal in version['improvement_signals']:
            if signal['kind']=='LOW_SELF_REPORTED_PROGRESS' and signal['text'] not in mapped_text:continue
            improvements.append({**signal,'course_version_id':version['course_version_id'],'course_title':version['course_title'],'version_number':version['version_number']})
    return {**skills.skill_data(db,skill),**summary(db,skill,actor),'coverage':coverage,
        'requests':[{'id':n.request_id,'title':title,'status':status or 'LEGACY','source':n.source,'active':n.active,'human_verified':n.human_verified} for n,title,status in needs],
        'content_improvement_signals':improvements,'can_manage':actor.role=='NEEDS_ANALYST',
        'meaning':'Katalogda ders bulunması ihtiyacın karşılandığı anlamına gelmez. Bunlar kanıt ve ihtiyaç sinyalleridir.'}
