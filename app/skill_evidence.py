"""Append-only, source-deduplicated observations. Completion never means proficiency."""
import hashlib
from sqlalchemy import select,func,or_,and_
from sqlalchemy.dialects.sqlite import insert
from .skill_models import SkillEvidence as Evidence,RequestSkillNeed as Need,CourseSkillMapping as Mapping,Skill
from .models import Enrollment,TrainingSession,CourseVersion,LearningEvaluation,RequestWorkflow,RequestReferral,PortalUser
from .utils import json_dumps,json_loads
from .time_policy import utc_now,utc_stamp,as_utc

LABELS={'REQUEST_NEED':'Doğrulanmış eğitim ihtiyacı','TRAINING_COMPLETION':'İlişkili eğitim tamamlandı',
    'SELF_EVALUATION':'Katılımcı öz değerlendirmesi','OUTCOME_EVALUATION':'Katılımcının ihtiyaç sonucu',
    'AUTHORIZED_VALIDATION':'Yetkili değerlendiricinin ihtiyaç sonucu'}
SIGNALS={'NONE':'Gelişmedi','PARTIAL':'Kısmen gelişti','CLEAR':'Belirgin gelişti',
    'RESOLVED':'İhtiyaç tamamen karşılandı','PARTIALLY_RESOLVED':'İhtiyaç kısmen karşılandı','NOT_RESOLVED':'İhtiyaç karşılanmadı'}


def emit(db,key,**values):
    db.execute(insert(Evidence).values(dedupe_key=hashlib.sha256(key.encode()).hexdigest(),**values)
        .on_conflict_do_nothing(index_elements=['dedupe_key']))


def from_need(db,row,flow):
    if not row.active or not row.human_verified or not flow or not flow.owner_hash.startswith('user:'):return
    owner=flow.owner_hash[5:]
    if not owner.isdecimal() or not db.get(PortalUser,int(owner)):return
    emit(db,f'need:{row.id}',user_id=int(owner),skill_id=row.skill_id,evidence_type='REQUEST_NEED',request_need_id=row.id,
        observed_at=row.verified_at,provenance_json=json_dumps({'source_entity':'REQUEST_SKILL_NEED','source_id':row.id,
            'request_id':row.request_id,'analysis_run_id':row.analysis_run_id,'verified_by':row.verified_by,'source':row.source}))


def from_completion(db,entry):
    from .evaluation import eligible
    if not eligible(entry):return
    session=db.get(TrainingSession,entry.session_id);version=db.get(CourseVersion,session.course_version_id)
    if version.state not in ('PUBLISHED','ARCHIVED'):return
    rows=db.scalars(select(Mapping).where(Mapping.course_version_id==version.id).order_by(Mapping.id))
    by_skill={}
    for row in rows:by_skill.setdefault(row.skill_id,[]).append(row)
    for skill_id,group in by_skill.items():
        emit(db,f'completion:{entry.id}:{utc_stamp(entry.completed_at)}:{skill_id}',user_id=entry.user_id,skill_id=skill_id,
            evidence_type='TRAINING_COMPLETION',course_version_id=version.id,mapping_id=group[0].id,enrollment_id=entry.id,
            observed_at=entry.completed_at,provenance_json=json_dumps({'source_entity':'ENROLLMENT','source_id':entry.id,
                'mapping_ids':[m.id for m in group],'session_id':session.id,'completion_at':utc_stamp(entry.completed_at),
                'meaning':'İlişkili eğitimi tamamladı; yetkinlik seviyesi doğrulanmış değildir.'}))


def from_evaluation(db,row):
    if row.status!='COMPLETED' or row.evaluation_type=='FEEDBACK':return
    entry=db.get(Enrollment,row.enrollment_id);answers=json_loads(row.response_json,{})
    maps=list(db.scalars(select(Mapping).where(Mapping.course_version_id==row.course_version_id).order_by(Mapping.id)))
    seen=set()
    for mapping in maps:
        if row.evaluation_type=='LEARNING':
            if mapping.outcome_index<0:continue
            signal=answers.get(f'outcome_{mapping.outcome_index}')
            if signal not in ('NONE','PARTIAL','CLEAR'):continue
            kind='SELF_EVALUATION';scope=str(mapping.outcome_index)
        else:
            signal=row.outcome
            if signal not in ('RESOLVED','PARTIALLY_RESOLVED','NOT_RESOLVED'):continue
            kind='AUTHORIZED_VALIDATION' if row.evaluator_source=='AUTHORIZED_REVIEWER' else 'OUTCOME_EVALUATION';scope='application'
        key=(mapping.skill_id,scope)
        if key in seen:continue
        seen.add(key)
        emit(db,f'evaluation:{row.id}:{mapping.skill_id}:{scope}',user_id=entry.user_id,skill_id=mapping.skill_id,
            evidence_type=kind,course_version_id=row.course_version_id,mapping_id=mapping.id,enrollment_id=entry.id,evaluation_id=row.id,
            signal=signal,observed_at=row.submitted_at,provenance_json=json_dumps({'source_entity':'EVALUATION','source_id':row.id,
                'evaluator_source':row.evaluator_source,'mapping_id':mapping.id,'outcome_index':mapping.outcome_index if kind=='SELF_EVALUATION' else None,
                'outcome_text':mapping.outcome_text if kind=='SELF_EVALUATION' else None,'completion_at':utc_stamp(row.completion_at),
                'meaning':'Öz bildirim / ilişkili ihtiyacın sonucu; tekil yetkinlik seviyesi değildir.'}))


def visible_aggregate(actor):
    """Scoped SQL predicates; no individual user record is returned by aggregates."""
    if actor.role=='NEEDS_ANALYST':return True
    needs=select(Need.id).join(RequestReferral,RequestReferral.request_id==Need.request_id).where(
        RequestReferral.department==actor.role,RequestReferral.active.is_(True),RequestReferral.training_need_confirmed.is_(True))
    enrollments=select(Enrollment.id).join(TrainingSession,TrainingSession.id==Enrollment.session_id).where(TrainingSession.responsible_unit==actor.role)
    return or_(Evidence.request_need_id.in_(needs),Evidence.enrollment_id.in_(enrollments))


def current(row,db):
    if row.request_need_id:
        need=db.get(Need,row.request_need_id);return bool(need and need.active and need.human_verified)
    entry=db.get(Enrollment,row.enrollment_id)
    if not entry or entry.status!='ENROLLED' or entry.completion!='COMPLETED':return False
    provenance=json_loads(row.provenance_json,{})
    return utc_stamp(entry.completed_at)==provenance.get('completion_at')


def evidence_data(db,row,actor):
    from .training import trace
    from .operations import can_see
    provenance=json_loads(row.provenance_json,{})
    result={'id':row.id,'skill_id':row.skill_id,'type':row.evidence_type,'label':LABELS[row.evidence_type],
        'signal':row.signal,'signal_label':SIGNALS.get(row.signal),'observed_at':utc_stamp(row.observed_at),
        'source_current':current(row,db),'provenance':provenance,'trace':{}}
    if row.enrollment_id:
        entry=db.get(Enrollment,row.enrollment_id);session=db.get(TrainingSession,entry.session_id);version=db.get(CourseVersion,row.course_version_id)
        result.update(course_title=version.title,course_version_number=version.version_number)
        result['trace']={**trace(db,session,actor),'session_id':session.id,'enrollment_id':entry.id,'evaluation_id':row.evaluation_id}
        person=db.get(PortalUser,actor.user_id)
        if entry.source_request_id and can_see(db,person,entry.source_request_id):result['trace']['need_request_id']=entry.source_request_id
        evaluation=db.get(LearningEvaluation,row.evaluation_id) if row.evaluation_id else None
        result['trace']['can_open_evaluation']=bool(evaluation and evaluation.evaluator_id==actor.user_id)
    elif row.request_need_id:
        need=db.get(Need,row.request_need_id)
        if can_see(db,db.get(PortalUser,actor.user_id),need.request_id):
            result['trace']={'need_request_id':need.request_id,'analysis_id':need.analysis_run_id,'verification_need_id':need.id}
    return result


def profile(db,actor,skill_id=None,offset=0,limit=20):
    from .skills import skill_data
    base=select(Evidence.skill_id).where(Evidence.user_id==actor.user_id)
    if skill_id:base=base.where(Evidence.skill_id==skill_id)
    grouped=base.group_by(Evidence.skill_id).subquery()
    query=select(Skill).where(Skill.id.in_(select(grouped.c.skill_id))).order_by(Skill.normalized_name).offset(offset).limit(limit)
    items=[]
    for skill in db.scalars(query):
        count,last=db.execute(select(func.count(),func.max(Evidence.observed_at)).where(Evidence.user_id==actor.user_id,Evidence.skill_id==skill.id)).one()
        need_count=db.scalar(select(func.count()).select_from(Need).join(RequestWorkflow,RequestWorkflow.request_id==Need.request_id).where(
            Need.skill_id==skill.id,Need.active.is_(True),Need.human_verified.is_(True),RequestWorkflow.owner_hash==f'user:{actor.user_id}',RequestWorkflow.status!='RESOLVED'))
        completed=db.scalar(select(func.count()).select_from(Evidence).join(Enrollment,Enrollment.id==Evidence.enrollment_id).where(
            Evidence.user_id==actor.user_id,Evidence.skill_id==skill.id,Evidence.evidence_type=='TRAINING_COMPLETION',Enrollment.status=='ENROLLED',Enrollment.completion=='COMPLETED'))
        signals=[]
        if need_count:signals.append(f'{need_count} açık talepte doğrulanmış yetkinlik ihtiyacı')
        if need_count and not completed:signals.append('İlişkili eğitim tamamlanma kanıtı henüz yok')
        if need_count>1:signals.append('Tekrarlayan ihtiyaç bildirimi var')
        unmet=db.scalar(select(func.count(func.distinct(Evidence.evaluation_id))).join(Enrollment,Enrollment.id==Evidence.enrollment_id)
            .join(LearningEvaluation,LearningEvaluation.id==Evidence.evaluation_id).where(Evidence.user_id==actor.user_id,
                Evidence.skill_id==skill.id,Evidence.signal.in_(('PARTIALLY_RESOLVED','NOT_RESOLVED')),
                Enrollment.status=='ENROLLED',Enrollment.completion=='COMPLETED',Enrollment.completed_at==LearningEvaluation.completion_at))
        if unmet:signals.append(f'{unmet} sonuç değerlendirmesinde ilişkili ihtiyaç kısmen karşılandı / karşılanmadı')
        items.append({**skill_data(db,skill),'evidence_count':count,'last_evidence_at':utc_stamp(last),'need_signals':signals})
    return {'items':items,'total':db.scalar(select(func.count()).select_from(grouped)),'offset':offset,'limit':limit,
        'meaning':'Eğitim ve sonuç kayıtlarınızın kanıtlarıdır; yetkinlik puanı veya performans değerlendirmesi değildir.'}


def own_evidence(db,actor,skill_id,offset,limit):
    query=select(Evidence).where(Evidence.user_id==actor.user_id,Evidence.skill_id==skill_id)
    return {'items':[evidence_data(db,row,actor) for row in db.scalars(query.order_by(Evidence.observed_at.desc(),Evidence.id.desc()).offset(offset).limit(limit))],
        'total':db.scalar(select(func.count()).select_from(query.subquery())),'offset':offset,'limit':limit}
