"""Synthetic relational fixtures, also used by the bounded portfolio benchmark."""
from datetime import timedelta
from sqlalchemy import select
from app.models import PortalUser,Course,CourseVersion,CourseCatalog,TrainingSession,Enrollment,LearningEvaluation,RequestRecord,RequestWorkflow
from app.skill_models import SkillGroup,Skill,CourseSkillMapping,RequestSkillNeed
from app.time_policy import utc_now
from app.utils import json_dumps

def seed(db,actor,people=10,skill_count=1,outcome='NOT_RESOLVED',version=None,repeat=True,progress='NONE'):
    now=utc_now();skills=[]
    for i in range(skill_count):
        name=f'Synthetic portfolio {db.query(Skill).count()}-{i}'
        s=Skill(canonical_name=name,normalized_name=name.lower(),group_id=db.scalar(select(SkillGroup.id)),created_by=actor.user_id)
        db.add(s);db.flush();skills.append(s)
    if version is None:
        c=Course(code='PORT-'+str(db.query(Course).count()),name='Synthetic portfolio content',pdf_path='synthetic.pdf')
        db.add(c);db.flush()
        version=CourseVersion(course_id=c.id,version_number=1,title=c.name,state='DRAFT',legacy=True,
            outcomes_json=json_dumps([{'id':'first','text':'Synthetic mapped outcome'}]))
        db.add(version);db.flush()
        for s in skills:
            for index in (-1,0):db.add(CourseSkillMapping(course_version_id=version.id,skill_id=s.id,outcome_index=index,outcome_text='Synthetic mapped outcome' if index==0 else None,created_by=actor.user_id))
        db.flush();version.state='PUBLISHED';db.flush()
        db.add(CourseCatalog(course_id=c.id,current_version_id=version.id,responsible_unit='TECHNICAL_DESIGN'));db.flush()
    session=TrainingSession(course_version_id=version.id,title='Synthetic training',responsible_unit='TECHNICAL_DESIGN',
        delivery_mode='ONLINE',status='COMPLETED',start_at=now-timedelta(days=4),end_at=now-timedelta(days=3),created_by=actor.user_id)
    db.add(session);db.flush();users=[];requests=[];entries=[]
    prefix=db.query(PortalUser).count()
    for i in range(people):
        user=PortalUser(username=f'portfolio-{prefix}-{i}',display_name=f'PRIVATE-EMPLOYEE-{prefix}-{i}',role='EMPLOYEE',password_salt='0'*32,password_hash='0'*64)
        db.add(user);db.flush();users.append(user)
        request=RequestRecord(text='Synthetic planning request',created_at=now if repeat else now-timedelta(days=10))
        db.add(request);db.flush();requests.append(request)
        db.add(RequestWorkflow(request_id=request.id,owner_hash=f'user:{user.id}',status='IN_REVIEW'))
        for s in skills:db.add(RequestSkillNeed(request_id=request.id,skill_id=s.id,source='MANUAL',human_verified=True,active=True,created_by=actor.user_id,verified_by=actor.user_id))
        entry=Enrollment(session_id=session.id,user_id=user.id,completion='COMPLETED',completed_at=now-timedelta(days=3))
        db.add(entry);db.flush();entries.append(entry)
        for source in ('PARTICIPANT','AUTHORIZED_REVIEWER'):
            db.add(LearningEvaluation(enrollment_id=entry.id,course_version_id=version.id,evaluation_type='APPLICATION',
                evaluator_source=source,evaluator_id=user.id if source=='PARTICIPANT' else actor.user_id,
                template_json='{}',completion_at=entry.completed_at,status='COMPLETED',submitted_at=now,
                response_json=json_dumps({'outcome':outcome,'comment':'PRIVATE-EVALUATION-COMMENT'}),outcome=outcome,created_by=actor.user_id))
        db.add(LearningEvaluation(enrollment_id=entry.id,course_version_id=version.id,evaluation_type='LEARNING',
            evaluator_source='PARTICIPANT',evaluator_id=user.id,template_json='{}',completion_at=entry.completed_at,
            status='COMPLETED',submitted_at=now,response_json=json_dumps({'outcome_0':progress,'comment':'PRIVATE-EVALUATION-COMMENT'}),created_by=actor.user_id))
    db.commit()
    return {'skills':skills,'version':version,'session':session,'users':users,'requests':requests,'entries':entries}
