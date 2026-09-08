"""Transactional learning feedback, immutable submissions and scoped aggregates."""
from datetime import timedelta
from fastapi import HTTPException
from sqlalchemy import select, update, func, and_, or_, case
from sqlalchemy.dialects.sqlite import insert
from .models import (Enrollment, TrainingSession, CourseVersion, PortalUser, RequestRecord,
    RequestWorkflow, RequestSolutionPlan, DevelopmentItem)
from .evaluation_models import LearningEvaluation as Evaluation, EvaluationEvent as Event, EvaluationDelivery as Delivery
from . import evaluation_policy as policy, training
from .time_policy import utc_now, utc_stamp, as_utc
from .utils import json_dumps, json_loads


def eligible(entry):
    return bool(entry and entry.status=='ENROLLED' and entry.completion=='COMPLETED' and entry.completed_at)


def reviewer_allowed(db,session,person,request_id):
    if not person or not person.active or person.role not in ('NEEDS_ANALYST',session.responsible_unit): return False
    if request_id:
        from .operations import can_see
        return can_see(db,person,request_id)
    return True


def evaluator_allowed(db,row):
    entry=db.get(Enrollment,row.enrollment_id);session=db.get(TrainingSession,entry.session_id)
    person=db.get(PortalUser,row.evaluator_id)
    if not person or not person.active: return False
    return entry.user_id==person.id if row.evaluator_source=='PARTICIPANT' else reviewer_allowed(db,session,person,row.source_request_id)


def create(db,entry,kind,actor,*,source='PARTICIPANT',evaluator_id=None,available_at=None,due_at=None):
    # Serialize with completion correction and concurrent phase creation.
    db.execute(update(Enrollment).where(Enrollment.id==entry.id).values(version=Enrollment.version))
    db.refresh(entry)
    if not eligible(entry): raise HTTPException(422,'Değerlendirme için tamamlanmış aktif katılım gerekir.')
    session=db.get(TrainingSession,entry.session_id)
    version=db.get(CourseVersion,session.course_version_id)
    person=db.get(PortalUser,evaluator_id or entry.user_id)
    if source=='PARTICIPANT':
        if not person or person.id!=entry.user_id or not person.active: raise HTTPException(422,'Katılımcının aktif hesabı gerekir.')
    elif source!='AUTHORIZED_REVIEWER' or not evaluator_id or not reviewer_allowed(db,session,person,entry.source_request_id):
        raise HTTPException(403,'Gerçek erişim yetkisi bulunan bir değerlendirici seçin.')
    if source=='AUTHORIZED_REVIEWER' and kind!='APPLICATION':
        raise HTTPException(422,'Katılımcı geri bildirimi ve öz değerlendirme yalnızca katılımcıya aittir.')
    if kind=='LEARNING' and not json_loads(version.outcomes_json,[]):
        raise HTTPException(422,'Bu ders sürümünde kayıtlı kazanım bulunmuyor.')
    explicit_available=available_at
    available_at=available_at or utc_now()
    if due_at and as_utc(due_at)<as_utc(available_at): raise HTTPException(422,'Son tarih başlangıçtan önce olamaz.')
    previous=db.scalar(select(Evaluation).where(Evaluation.enrollment_id==entry.id,Evaluation.evaluation_type==kind,Evaluation.evaluator_source==source))
    if previous:
        if previous.evaluator_id!=person.id: raise HTTPException(409,'Bu aşamanın değerlendiricisi daha önce belirlenmiş.')
        if (explicit_available and as_utc(explicit_available)!=as_utc(previous.available_at)) or (due_at and as_utc(due_at)!=as_utc(previous.due_at)):
            raise HTTPException(409,'Bu değerlendirme aşaması zaten planlandı; mevcut tarihleri değerlendirme kaydından kontrol edin.')
        return previous
    row=Evaluation(enrollment_id=entry.id,course_version_id=version.id,source_request_id=entry.source_request_id,
        evaluation_type=kind,evaluator_source=source,evaluator_id=person.id,template_json=json_dumps(policy.template(kind,version)),
        completion_at=entry.completed_at,available_at=available_at,due_at=due_at,created_by=training.uid(actor))
    db.add(row);db.flush()
    event=Event(evaluation_id=row.id,version=row.version,action='CREATED',actor_id=training.uid(actor),actor_name=actor.display_name)
    db.add(event);db.flush()
    db.execute(insert(Delivery).values(evaluation_id=row.id,source_event_id=event.id,recipient_id=person.id,deliver_at=available_at)
        .on_conflict_do_nothing(index_elements=['evaluation_id']))
    dispatch(db)
    return row


def on_completion(db,entry,actor):
    """Runs inside the existing completion transaction; never performs a network call."""
    if not eligible(entry): return
    from .skill_evidence import from_completion
    from_completion(db,entry)
    person=db.get(PortalUser,entry.user_id)
    if not person or not person.active: return
    version=db.get(CourseVersion,db.get(TrainingSession,entry.session_id).course_version_id)
    for kind,spec in policy.TEMPLATES.items():
        if kind=='LEARNING' and not json_loads(version.outcomes_json,[]): continue
        delay=policy.FOLLOW_UP_DELAYS.get(kind)
        if spec['timing']=='immediate': create(db,entry,kind,actor)
        elif isinstance(delay,timedelta) and delay.total_seconds()>=0:
            create(db,entry,kind,actor,available_at=as_utc(entry.completed_at)+delay)


def dispatch(db):
    # Conditional publication is idempotent across worker restarts and processes.
    db.execute(update(Delivery).where(Delivery.processed_at.is_(None),Delivery.deliver_at<=utc_now(),
        Delivery.evaluation_id.in_(select(Evaluation.id).join(Enrollment,Enrollment.id==Evaluation.enrollment_id).where(
            Evaluation.status=='PENDING',Enrollment.status=='ENROLLED',Enrollment.completion=='COMPLETED')))
        .values(processed_at=utc_now()))


def load(db,identifier,actor):
    row=db.get(Evaluation,identifier)
    if not row or row.evaluator_id!=training.uid(actor) or not evaluator_allowed(db,row):
        raise HTTPException(404,'Değerlendirme bulunamadı.')
    return row


def brief(db,row):
    entry=db.get(Enrollment,row.enrollment_id);session=db.get(TrainingSession,entry.session_id);version=db.get(CourseVersion,row.course_version_id)
    return {'id':row.id,'enrollment_id':entry.id,'session_id':session.id,'session_title':session.title,
        'course_version_id':version.id,'course_version_number':version.version_number,'course_title':version.title,
        'evaluation_type':row.evaluation_type,'title':policy.TEMPLATES[row.evaluation_type]['title'],
        'evaluator_source':row.evaluator_source,'evaluator_source_label':policy.SOURCES[row.evaluator_source],
        'status':row.status,'status_label':policy.STATES[row.status],'version':row.version,
        'available_at':utc_stamp(row.available_at),'due_at':utc_stamp(row.due_at),'submitted_at':utc_stamp(row.submitted_at),
        'completion_at':utc_stamp(row.completion_at),'completion_current':eligible(entry),
        'outcome':row.outcome,'outcome_label':policy.OUTCOMES.get(row.outcome)}


def detail(db,row,actor):
    entry=db.get(Enrollment,row.enrollment_id);session=db.get(TrainingSession,entry.session_id)
    context=None
    if row.source_request_id:
        from .operations import can_see
        person=db.get(PortalUser,training.uid(actor))
        if can_see(db,person,row.source_request_id):
            request=db.get(RequestRecord,row.source_request_id);plan=db.get(RequestSolutionPlan,request.id)
            context={'id':request.id,'title':request.topic,'problem':request.text,'expected_output':plan.summary if plan else None}
    return {**brief(db,row),'template':json_loads(row.template_json,{}),'answers':json_loads(row.response_json,{}) if row.response_json else None,
        'can_submit':row.status=='PENDING' and eligible(entry) and as_utc(row.available_at)<=utc_now(),
        'source_request':context,'trace':training.trace(db,session,actor),
        'history':[{'action':e.action,'actor':e.actor_name,'at':utc_stamp(e.created_at)} for e in db.scalars(select(Event).where(Event.evaluation_id==row.id).order_by(Event.id))]}


def validate_answers(row,answers):
    questions=json_loads(row.template_json,{})['questions'];known={q['id'] for q in questions}
    if set(answers)-known: raise HTTPException(422,'Şablonda bulunmayan soru gönderilemez.')
    clean={}
    for q in questions:
        value=answers.get(q['id'])
        if value is None or value=='':
            if q.get('required',True): raise HTTPException(422,f"Lütfen yanıtlayın: {q['label']}")
            continue
        if q['type']=='rating':
            if type(value) is not int or not q['min']<=value<=q['max']: raise HTTPException(422,'Geçerli değerlendirme puanı seçin.')
        elif q['type'] in ('single_choice','outcome_rating'):
            if not isinstance(value,str) or value not in q['options']: raise HTTPException(422,'Geçerli bir seçenek seçin.')
        elif q['type']=='free_text':
            if not isinstance(value,str) or len(value)>q['max_length']: raise HTTPException(422,'Açıklama en fazla 3000 karakter olmalıdır.')
            value=value.strip()
        clean[q['id']]=value
    return clean


def submit(db,row,actor,payload):
    entry=db.get(Enrollment,row.enrollment_id)
    db.execute(update(Enrollment).where(Enrollment.id==entry.id).values(version=Enrollment.version));db.refresh(entry)
    if not eligible(entry) or as_utc(row.available_at)>utc_now(): raise HTTPException(422,'Değerlendirme henüz yanıtlanabilir durumda değil.')
    if not evaluator_allowed(db,row): raise HTTPException(403,'Değerlendirici erişimi değişti.')
    if row.status!='PENDING': raise HTTPException(409,'Gönderilmiş değerlendirme değiştirilemez.')
    answers=validate_answers(row,payload.answers)
    now=utc_now()
    changed=db.execute(update(Evaluation).where(Evaluation.id==row.id,Evaluation.status=='PENDING',Evaluation.version==payload.expected_version)
        .values(status='COMPLETED',version=Evaluation.version+1,submitted_at=now,response_json=json_dumps(answers),outcome=answers.get('outcome')))
    if changed.rowcount!=1: raise HTTPException(409,'Değerlendirme başka bir işlemde güncellendi.')
    db.refresh(row)
    db.add(Event(evaluation_id=row.id,version=row.version,action='SUBMITTED',actor_id=training.uid(actor),actor_name=actor.display_name))
    db.execute(update(Delivery).where(Delivery.evaluation_id==row.id,Delivery.read_at.is_(None)).values(read_at=now))
    from .skill_evidence import from_evaluation
    from_evaluation(db,row)
    db.commit()
    return detail(db,row,actor)


def reviewer_sql():
    # Same named-role/referral visibility as reviewer_allowed (no inferred HR manager).
    return """(v.evaluator_source='PARTICIPANT' OR (:role IN ('NEEDS_ANALYST',s.responsible_unit)
      AND (v.source_request_id IS NULL OR :role='NEEDS_ANALYST' OR EXISTS
      (SELECT 1 FROM request_referrals r WHERE r.request_id=v.source_request_id AND r.department=:role AND r.active=1 AND r.training_need_confirmed=1))))"""


def inbox_sql():
    return """SELECT 'evaluation' kind,v.id,coalesce(v.source_request_id,0) request_id,0 did,4 kind_order,0 tie_group,v.available_at stage_at
     FROM learning_evaluations v JOIN training_enrollments e ON e.id=v.enrollment_id
     JOIN training_sessions s ON s.id=e.session_id
     WHERE v.evaluator_id=:uid AND v.status='PENDING' AND v.available_at<=:now
     AND e.status='ENROLLED' AND e.completion='COMPLETED' AND e.completed_at IS NOT NULL
     AND EXISTS (SELECT 1 FROM portal_users WHERE id=:uid AND active=1) AND """+reviewer_sql()


def inbox_item(db,identifier,actor):
    row=load(db,identifier,actor);entry=brief(db,row)
    return {**entry,'kind':'evaluation','evaluation_id':row.id,'request_id':row.source_request_id or 0,
        'title':entry['title']+' · '+entry['course_title'],'topic':entry['course_title'],
        'work_type_label':'Eğitim değerlendirmesi','state':row.status,'state_label':policy.STATES[row.status],
        'action_required':'Değerlendirmenizi gönderin','responsible_unit_label':policy.SOURCES[row.evaluator_source],
        'updated_at':utc_stamp(row.available_at),'aging':{'current_stage_seconds':max(0,int((utc_now()-as_utc(row.available_at)).total_seconds()))},
        'delegation':None,'assignee':training.user_info(db,row.evaluator_id)}


def list_evaluations(db,actor,status,offset,limit):
    # Evaluator-only list. A revoked reviewer can see neither the response nor the title.
    query=select(Evaluation).join(Enrollment,Enrollment.id==Evaluation.enrollment_id).join(TrainingSession,TrainingSession.id==Enrollment.session_id)
    from .models import RequestReferral
    reviewer=or_(Evaluation.source_request_id.is_(None),actor.role=='NEEDS_ANALYST',select(RequestReferral.request_id).where(
        RequestReferral.request_id==Evaluation.source_request_id,RequestReferral.department==actor.role,RequestReferral.active.is_(True),RequestReferral.training_need_confirmed.is_(True)).exists())
    query=query.where(Evaluation.evaluator_id==training.uid(actor),or_(Evaluation.evaluator_source=='PARTICIPANT',
        and_(or_(actor.role=='NEEDS_ANALYST',TrainingSession.responsible_unit==actor.role),reviewer)))
    if status: query=query.where(Evaluation.status==status)
    return {'items':[brief(db,r) for r in db.scalars(query.order_by(Evaluation.status.desc(),Evaluation.available_at,Evaluation.id).offset(offset).limit(limit))],
        'total':db.scalar(select(func.count()).select_from(query.subquery())),'offset':offset,'limit':limit}


def notice_payload(db,note,actor):
    row=db.get(Evaluation,note.evaluation_id)
    accessible=row and evaluator_allowed(db,row) and row.evaluator_id==training.uid(actor)
    return {'id':f'evaluation:{note.id}','evaluation_id':row.id if accessible else None,'request_id':None,
        'title':('Yetkili sonuç doğrulaması bekleniyor' if row.evaluator_source=='AUTHORIZED_REVIEWER' else policy.TEMPLATES[row.evaluation_type]['title']+' bekleniyor') if accessible else 'Değerlendirme erişiminiz değişti',
        'message':'Eğitim sonrası deneyiminizi ve ihtiyaç sonucunu kaydedin.' if accessible else 'Bu değerlendirmeye güncel erişiminiz bulunmuyor.',
        'created_at':utc_stamp(note.processed_at),'read_at':utc_stamp(note.read_at),'importance':'normal'}


def aggregate(db,actor,*,session_id=None,course_version_id=None):
    """Version-scoped SQL aggregates; individual comments never leave this boundary."""
    base=select(Evaluation,Enrollment.session_id).join(Enrollment,Enrollment.id==Evaluation.enrollment_id).join(TrainingSession,TrainingSession.id==Enrollment.session_id)
    base=base.where(or_(actor.role=='NEEDS_ANALYST',TrainingSession.responsible_unit==actor.role),
        Enrollment.status=='ENROLLED',Enrollment.completion=='COMPLETED')
    if session_id: base=base.where(TrainingSession.id==session_id)
    if course_version_id: base=base.where(Evaluation.course_version_id==course_version_id)
    rows=base.subquery()
    # Count phases explicitly. Different phases and reviewer sources are not blended.
    counts=db.execute(select(rows.c.course_version_id,rows.c.evaluation_type,rows.c.evaluator_source,rows.c.status,func.count())
        .group_by(rows.c.course_version_id,rows.c.evaluation_type,rows.c.evaluator_source,rows.c.status)).all()
    versions={}
    for vid,kind,source,status,n in counts:
        if vid not in versions:
            v=db.get(CourseVersion,vid)
            versions[vid]={'course_version_id':vid,'course_title':v.title,'version_number':v.version_number,'pending':0,'completed':0,'phases':[],
                'outcomes':[],'learning_signals':[],'improvement_signals':[],'participant_rating':None,'feedback_count':0}
        item=versions[vid];item['pending' if status=='PENDING' else 'completed']+=n
        item['phases'].append({'type':kind,'source':source,'status':status,'count':n})
    feedback=db.execute(select(rows.c.course_version_id,func.count(),func.avg(func.json_extract(rows.c.response_json,'$.overall')))
        .where(rows.c.status=='COMPLETED',rows.c.evaluation_type=='FEEDBACK',rows.c.evaluator_source=='PARTICIPANT').group_by(rows.c.course_version_id)).all()
    for vid,n,avg in feedback: versions[vid].update(feedback_count=n,participant_rating=round(avg,2) if avg is not None else None)
    for vid,source,outcome,n in db.execute(select(rows.c.course_version_id,rows.c.evaluator_source,rows.c.outcome,func.count())
        .where(rows.c.status=='COMPLETED',rows.c.evaluation_type=='APPLICATION').group_by(rows.c.course_version_id,rows.c.evaluator_source,rows.c.outcome)):
        versions[vid]['outcomes'].append({'source':source,'outcome':outcome,'label':policy.OUTCOMES.get(outcome),'count':n})
    for vid,item in versions.items():
        version=db.get(CourseVersion,vid)
        for i,outcome in enumerate(json_loads(version.outcomes_json,[])):
            answer=func.json_extract(rows.c.response_json,f'$.outcome_{i}')
            values=db.execute(select(answer,func.count()).where(rows.c.course_version_id==vid,rows.c.status=='COMPLETED',
                rows.c.evaluation_type=='LEARNING',rows.c.evaluator_source=='PARTICIPANT').group_by(answer)).all()
            distribution=[{'value':v,'label':policy.PROGRESS.get(v),'count':n} for v,n in values if v]
            if distribution:item['learning_signals'].append({'outcome':outcome['text'],'distribution':distribution})
            low=sum(n for v,n in values if v=='NONE')
            if low>=policy.REPEATED_SIGNAL_COUNT:item['improvement_signals'].append({'kind':'LOW_SELF_REPORTED_PROGRESS','text':outcome['text'],'count':low,'source':'PARTICIPANT'})
        for source in policy.SOURCES:
            low=sum(r['count'] for r in item['outcomes'] if r['source']==source and r['outcome'] in ('PARTIALLY_RESOLVED','NOT_RESOLVED'))
            if low>=policy.REPEATED_SIGNAL_COUNT:item['improvement_signals'].append({'kind':'UNMET_NEED','text':'Tekrarlayan kısmi / karşılanmamış ihtiyaç bildirimi','count':low,'source':source})
        total=db.scalar(select(func.count()).select_from(rows).where(rows.c.course_version_id==vid,rows.c.available_at<=utc_now()))
        item['response_rate']=round(100*item['completed']/total,1) if total>=policy.MIN_PERCENT_SAMPLE else None
        item['response_eligible_count']=total
        eq=select(func.count()).select_from(Enrollment).join(TrainingSession,TrainingSession.id==Enrollment.session_id).where(
            TrainingSession.course_version_id==vid,Enrollment.completion=='COMPLETED',Enrollment.status=='ENROLLED',
            or_(actor.role=='NEEDS_ANALYST',TrainingSession.responsible_unit==actor.role))
        if session_id:eq=eq.where(TrainingSession.id==session_id)
        item['completed_enrollments']=db.scalar(eq)
    return {'versions':list(versions.values()),'empty_label':'Henüz değerlendirme verisi yok',
        'meaning':'Katılımcı bildirimleri ve yetkili gözlemleri; talep kapatma veya yetkinlik puanı değildir.'}


def request_outcomes(db,request_id):
    # Invoked only by the already-authorized request detail. Never expose free text.
    rows=db.scalars(select(Evaluation).where(Evaluation.source_request_id==request_id).order_by(Evaluation.created_at,Evaluation.id))
    return [brief(db,row) for row in rows]
