import unittest
from datetime import timedelta
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
from sqlalchemy import select, update, text
from sqlalchemy.exc import IntegrityError
import test_training as fixtures
from app import evaluation, evaluation_policy, operations
from app.evaluation_models import LearningEvaluation as Evaluation, EvaluationEvent, EvaluationDelivery
from app.evaluation_schemas import EvaluationSubmit
from app.models import (Enrollment, Course, CourseVersion, CourseCatalog, PortalUser, RequestWorkflow,
    DevelopmentItem, RequestDecision, TrainingSession)
from app.time_policy import utc_now
from app.utils import json_dumps


class EvaluationTests(unittest.TestCase):
    setUp=fixtures.TrainingTests.setUp
    tearDown=fixtures.TrainingTests.tearDown
    case=fixtures.TrainingTests.case
    delegate=fixtures.TrainingTests.delegate
    count=fixtures.TrainingTests.count
    make=fixtures.TrainingTests.make
    action=fixtures.TrainingTests.action
    enroll=fixtures.TrainingTests.enroll
    result=fixtures.TrainingTests.result

    def catalog(self,**kwargs):
        c=Course(code='EVAL-'+str(self.count(Course)),name='Synthetic feedback course',pdf_path='synthetic.pdf')
        self.db.add(c);self.db.flush()
        v=CourseVersion(course_id=c.id,version_number=1,title=c.name,state='PUBLISHED',legacy=True,
            outcomes_json=json_dumps([{'id':'original','text':'Sentetik otomasyon geliştirmek'}]))
        self.db.add(v);self.db.flush();self.db.add(CourseCatalog(course_id=c.id,current_version_id=v.id,responsible_unit='TECHNICAL_DESIGN'));self.db.commit()
        return v

    def completed(self,source=False,users=('employee',),version=None):
        r,f=self.case('ACTION_PLANNED','TECHNICAL_DESIGN') if source else (None,None)
        row=self.make(version)
        for user in users: row=self.enroll(row,user,**({'source_request_id':r.id} if source and user=='employee' else {}))
        row=self.action(row,'SCHEDULE');row=self.action(row,'START');row=self.result(row,'completion','COMPLETED')
        return row,r,f

    def evaluations(self):
        self.db.expire_all();return list(self.db.scalars(select(Evaluation).order_by(Evaluation.id)))

    def plan(self,row,source='PARTICIPANT',**kwargs):
        self.actor=self.people['tech']
        response=self.client.post('/api/evaluations',json={'enrollment_id':row['enrollments'][0]['id'],
            'evaluation_type':'APPLICATION','evaluator_source':source,**kwargs})
        self.assertEqual(response.status_code,201,response.text);return response.json()

    def answers(self,row,**overrides):
        spec=__import__('json').loads(row.template_json)
        values={q['id']:4 if q['type']=='rating' else 'Private synthetic comment' if q['type']=='free_text' else next(iter(q['options'])) for q in spec['questions']}
        return {**values,**overrides}

    def send(self,row,user='employee',status=200,**overrides):
        self.actor=self.people[user]
        response=self.client.post(f'/api/evaluations/{row.id}/submit',json={'expected_version':row.version,'answers':self.answers(row,**overrides)})
        self.assertEqual(response.status_code,status,response.text);return response.json()

    def test_completed_creates_immediate_only_and_no_duplicate(self):
        row,_,_=self.completed();items=self.evaluations()
        self.assertEqual([x.evaluation_type for x in items],['FEEDBACK','LEARNING'])
        entry=self.db.get(Enrollment,row['enrollments'][0]['id'])
        evaluation.on_completion(self.db,entry,self.people['tech']);self.db.commit()
        self.assertEqual(self.count(Evaluation),2);self.assertEqual(self.count(EvaluationDelivery),2)
        self.assertEqual(self.count(EvaluationEvent),2)

    def test_incomplete_and_removed_rejected(self):
        row=self.make();row=self.enroll(row)
        for state in ('ENROLLED','REMOVED'):
            self.db.execute(update(Enrollment).values(status=state));self.db.commit()
            result=self.client.post('/api/evaluations',json={'enrollment_id':row['enrollments'][0]['id'],'evaluation_type':'FEEDBACK'})
            self.assertEqual(result.status_code,422)

    def test_own_response_only_and_comments_private(self):
        row,_,_=self.completed(users=('employee','employee2'));item=self.evaluations()[0]
        self.send(item,'employee2',404)
        self.send(item,comment='PRIVATE-COMMENT-ONLY-OWNER')
        for user in ('employee2','tech','analyst','engineering'):
            self.actor=self.people[user]
            self.assertEqual(self.client.get(f'/api/evaluations/{item.id}').status_code,404)
            for url in ('/api/evaluations','/api/evaluations/report',f"/api/training/{row['id']}"):
                self.assertNotIn('PRIVATE-COMMENT-ONLY-OWNER',self.client.get(url).text)

    def test_immutable_submission_and_audit(self):
        self.completed();item=self.evaluations()[0];sent=self.send(item)
        self.assertEqual(sent['history'][-1]['actor'],'employee');self.assertTrue(sent['submitted_at'])
        self.send(item,status=409)
        for sql in (f"UPDATE learning_evaluations SET response_json='{{}}' WHERE id={item.id}",
                    f"DELETE FROM learning_evaluations WHERE id={item.id}",
                    'UPDATE evaluation_events SET actor_name=\'changed\''):
            with self.assertRaises(IntegrityError):self.db.execute(text(sql));self.db.commit()
            self.db.rollback()

    def test_pending_context_cannot_be_reassigned(self):
        self.completed();item=self.evaluations()[0]
        with self.assertRaises(IntegrityError):
            self.db.execute(update(Evaluation).where(Evaluation.id==item.id).values(evaluator_id=self.people['employee2'].user_id));self.db.commit()
        self.db.rollback()

    def test_invalid_unknown_missing_and_boolean_answers(self):
        self.completed();item=self.evaluations()[0]
        self.send(item,status=422,overall=True);self.send(item,status=422,overall=6)
        self.send(item,status=422,unknown='x');self.send(item,status=422,comment='x'*3001)
        self.actor=self.people['employee']
        response=self.client.post(f'/api/evaluations/{item.id}/submit',json={'expected_version':1,'answers':{}})
        self.assertEqual(response.status_code,422);self.assertEqual(self.db.get(Evaluation,item.id).status,'PENDING')

    def test_stale_version_keeps_response_pending(self):
        self.completed();item=self.evaluations()[0];self.actor=self.people['employee']
        response=self.client.post(f'/api/evaluations/{item.id}/submit',json={'expected_version':22,'answers':self.answers(item)})
        self.assertEqual(response.status_code,409);self.db.expire_all();self.assertIsNone(self.db.get(Evaluation,item.id).response_json)

    def test_outcome_does_not_close_request_or_create_development(self):
        row,r,f=self.completed(source=True);plan=self.plan(row);item=self.db.get(Evaluation,plan['id'])
        before=self.count(DevelopmentItem);sent=self.send(item,outcome='RESOLVED',problem_persists='NO')
        self.db.expire_all();self.assertEqual(self.db.get(RequestWorkflow,r.id).status,'ACTION_PLANNED')
        self.assertEqual(self.count(DevelopmentItem),before)
        self.assertEqual(sent['source_request']['id'],r.id);self.assertIn('Sentetik',sent['source_request']['problem'])
        self.actor=self.people['tech'];detail=self.client.get(f'/api/admin/requests/{r.id}').json()
        self.assertEqual(detail['effectiveness'][-1]['outcome'],'RESOLVED')
        self.assertNotIn('Private synthetic comment',str(detail['effectiveness']))

    def test_delayed_delivery_survives_retry_and_no_early_action(self):
        row,_,_=self.completed();future=utc_now()+timedelta(days=12)
        planned=self.plan(row,available_at=future.isoformat(),due_at=(future+timedelta(days=2)).isoformat())
        item=self.db.get(Evaluation,planned['id']);self.send(item,status=422)
        actor=self.people['employee']
        self.assertNotIn(item.id,[x.get('evaluation_id') for x in operations.inbox(self.db,actor,0,100)['items']])
        self.assertNotIn(item.id,[x.get('evaluation_id') for x in operations.notifications(self.db,actor,0,100)['items']])
        with patch('app.evaluation.utc_now',return_value=future+timedelta(seconds=1)):
            evaluation.dispatch(self.db);evaluation.dispatch(self.db);self.db.commit()
        notes=operations.notifications(self.db,actor,0,100)['items']
        self.assertEqual(sum(x.get('evaluation_id')==item.id for x in notes),1)

    def test_manual_due_date_validation(self):
        row,_,_=self.completed();self.actor=self.people['tech']
        result=self.client.post('/api/evaluations',json={'enrollment_id':row['enrollments'][0]['id'],'evaluation_type':'APPLICATION',
            'available_at':'2026-11-02T10:00:00Z','due_at':'2026-11-01T10:00:00Z'})
        self.assertEqual(result.status_code,422)

    def test_optional_policy_and_duplicate_followup(self):
        with patch.dict(evaluation_policy.FOLLOW_UP_DELAYS,{'APPLICATION':timedelta(days=4)}):row,_,_=self.completed()
        items=self.evaluations();self.assertEqual(len(items),3)
        self.assertGreater(items[-1].available_at,utc_now())

    def test_authorized_reviewer_and_revoked_access(self):
        row,_,_=self.completed(source=True)
        plan=self.plan(row,'AUTHORIZED_REVIEWER',evaluator_id=self.people['tech2'].user_id)
        item=self.db.get(Evaluation,plan['id'])
        self.send(item,'employee',404)
        self.actor=self.people['tech2'];self.assertEqual(self.client.get(f'/api/evaluations/{item.id}').status_code,200)
        self.db.execute(update(PortalUser).where(PortalUser.id==self.actor.user_id).values(role='ENGINEERING_DESIGN'));self.db.commit()
        self.assertEqual(self.client.get(f'/api/evaluations/{item.id}').status_code,404)

    def test_no_fake_or_wrong_role_reviewer(self):
        row,_,_=self.completed(source=True);self.actor=self.people['tech']
        for user in (9999,self.people['engineering'].user_id,self.people['employee2'].user_id):
            response=self.client.post('/api/evaluations',json={'enrollment_id':row['enrollments'][0]['id'],
                'evaluation_type':'APPLICATION','evaluator_source':'AUTHORIZED_REVIEWER','evaluator_id':user})
            self.assertEqual(response.status_code,403)

    def test_notifications_inbox_read_scope_and_count(self):
        self.completed();items=self.evaluations();actor=self.people['employee'];self.actor=actor
        inbox=operations.inbox(self.db,actor,0,100)
        self.assertEqual({x['evaluation_id'] for x in inbox['items'] if x.get('kind')=='evaluation'},{i.id for i in items})
        notes=operations.notifications(self.db,actor,0,100)['items'];note=next(x for x in notes if x.get('evaluation_id'))
        self.actor=self.people['employee2'];self.assertEqual(self.client.post(f"/api/operations/notifications/{note['id']}/read").status_code,404)
        self.actor=actor;self.assertEqual(self.client.post(f"/api/operations/notifications/{note['id']}/read").status_code,200)
        self.client.post('/api/operations/notifications/read-all');self.assertEqual(self.client.get('/api/operations/notifications/count').json()['unread_count'],0)

    def test_version_immutability_and_analytics_partition(self):
        row,_,_=self.completed();items=self.evaluations();self.send(items[0],overall=2);self.send(items[1],outcome_0='NONE')
        old=self.db.get(CourseVersion,row['course_version_id']);old.state='ARCHIVED';old.revision+=1;self.db.flush()
        newer=CourseVersion(course_id=old.course_id,version_number=2,title='Newer synthetic version',state='PUBLISHED',legacy=True,
            outcomes_json=json_dumps([{'id':'new','text':'Yeni sürüm kazanımı'}]))
        self.db.add(newer);self.db.flush();self.db.get(CourseCatalog,old.course_id).current_version_id=newer.id;self.db.commit()
        self.completed(version=newer);newitems=self.evaluations()[2:];self.send(newitems[0],overall=5)
        data=evaluation.aggregate(self.db,self.people['tech'])['versions'];byid={r['course_version_id']:r for r in data}
        self.assertEqual(byid[old.id]['participant_rating'],2);self.assertEqual(byid[newer.id]['participant_rating'],5)
        self.assertIn('Sentetik otomasyon',self.db.get(Evaluation,items[1].id).template_json)
        self.assertNotIn('Yeni sürüm kazanımı',self.db.get(Evaluation,items[1].id).template_json)
        self.assertIsNone(byid[old.id]['response_rate'])

    def test_repeated_signal_is_evidence_not_automatic_work(self):
        row,_,_=self.completed(users=('employee','employee2'));items=self.evaluations()
        for item in items:
            if item.evaluation_type=='LEARNING':self.send(item,'employee' if item.evaluator_id==self.people['employee'].user_id else 'employee2',outcome_0='NONE')
        before=self.count(DevelopmentItem)
        data=evaluation.aggregate(self.db,self.people['tech'])['versions'][0]
        self.assertEqual(data['improvement_signals'][0]['count'],2);self.assertEqual(self.count(DevelopmentItem),before)
        self.assertEqual(evaluation.aggregate(self.db,self.people['engineering'])['versions'],[])
        self.assertEqual(evaluation.aggregate(self.db,self.people['employee'])['versions'],[])

    def test_completion_correction_retains_history_but_stops_pending_work(self):
        row,_,_=self.completed();items=self.evaluations();self.send(items[0])
        self.actor=self.people['tech'];self.result(row,'completion','NOT_COMPLETED')
        self.actor=self.people['employee'];self.send(items[1],status=422)
        self.assertFalse(self.client.get(f'/api/evaluations/{items[0].id}').json()['completion_current'])
        self.assertFalse(any(x.get('kind')=='evaluation' for x in operations.inbox(self.db,self.actor,0,100)['items']))

    def test_empty_aggregate_and_no_outcomes_legacy(self):
        self.assertEqual(evaluation.aggregate(self.db,self.people['tech'])['versions'],[])
        version=fixtures.TrainingTests.catalog(self)
        self.completed(version=version)
        self.assertEqual([x.evaluation_type for x in self.evaluations()],['FEEDBACK'])

    def test_sql_pagination_with_evaluations(self):
        self.completed(users=('employee','employee2'));actor=self.people['employee']
        allrows=operations.inbox(self.db,actor,0,100)
        for offset in range(allrows['total']+1):
            page=operations.inbox(self.db,actor,offset,1)
            self.assertEqual([r.get('evaluation_id') for r in page['items']],[r.get('evaluation_id') for r in allrows['items'][offset:offset+1]])

    def test_concurrent_creation_is_one_phase_one_notification(self):
        row,_,_=self.completed();identifier=row['enrollments'][0]['id']
        def create():
            with self.factory() as db:
                value=evaluation.create(db,db.get(Enrollment,identifier),'APPLICATION',self.people['tech']);db.commit();return value.id
        with ThreadPoolExecutor(max_workers=2) as pool:ids=list(pool.map(lambda _:create(),range(2)))
        self.assertEqual(ids[0],ids[1]);self.assertEqual(self.count(Evaluation),3);self.assertEqual(self.count(EvaluationDelivery),3)

    def test_concurrent_submit_keeps_one_audited_response(self):
        from fastapi import HTTPException
        self.completed();item=self.evaluations()[0];answers=self.answers(item)
        def submit():
            with self.factory() as db:
                try:
                    row=evaluation.load(db,item.id,self.people['employee'])
                    evaluation.submit(db,row,self.people['employee'],EvaluationSubmit(expected_version=1,answers=answers));return 200
                except HTTPException as e:return e.status_code
        with ThreadPoolExecutor(max_workers=2) as pool:codes=list(pool.map(lambda _:submit(),range(2)))
        self.assertEqual(sorted(codes),[200,409]);self.assertEqual(self.count(EvaluationEvent),3)

    def test_delegate_can_plan_but_cannot_answer_for_participant(self):
        row,_,_=self.completed()
        self.db.execute(update(TrainingSession).where(TrainingSession.id==row['id']).values(coordinator_id=self.people['tech'].user_id));self.db.commit()
        grant=self.delegate('tech','tech2');self.actor=self.people['tech2']
        payload={'enrollment_id':row['enrollments'][0]['id'],'evaluation_type':'APPLICATION'}
        self.assertEqual(self.client.post('/api/evaluations',json=payload).status_code,403)
        response=self.client.post('/api/evaluations',json=payload,headers={'X-Delegation-ID':str(grant['id'])})
        self.assertEqual(response.status_code,201,response.text)
        self.assertEqual(self.client.get(f"/api/evaluations/{response.json()['id']}").status_code,404)

    def test_anonymous_evaluation_routes_require_account(self):
        from app.main import app
        from app.portal_auth import current_account
        app.dependency_overrides[current_account]=lambda:None
        for url in ('/api/evaluations','/api/evaluations/report','/api/evaluations/1'):
            self.assertEqual(self.client.get(url).status_code,401)


class EvaluationTraceTests(unittest.TestCase):
    # Reuse the existing real publication workflow fixture, without duplicating it.
    for _name in ('setUp','tearDown','case','count','create','edit_payload','edit','action','ready','finish','draft','metadata','publish_action','published','source'):
        locals()[_name]=getattr(fixtures.TrainingTraceTests,_name)

    def source(self,enrichment=False,assignee=None):
        from app.models import AnalysisRun,DecisionAnalysisLink
        record,flow,payload=fixtures.TrainingTraceTests.source(self,enrichment,assignee)
        run=AnalysisRun(request_id=record.id,sequence=1,status='COMPLETED',trigger='IMPORTED',input_json='{}',result_json=flow.result_json)
        self.db.add(run);self.db.flush();self.db.add(DecisionAnalysisLink(decision_id=self.decision_id,analysis_run_id=run.id));self.db.commit()
        self.analysis_id=run.id
        return record,flow,payload

    def test_request_decision_development_version_enrollment_evaluation_chain(self):
        fixtures.TrainingTraceTests.test_end_to_end_request_decision_development_version_session_completion(self)
        entry=self.db.scalar(select(Enrollment));row=evaluation.create(self.db,entry,'APPLICATION',self.people['tech']);self.db.commit()
        data=evaluation.detail(self.db,row,self.people['employee'])
        self.assertEqual(data['source_request']['id'],entry.source_request_id)
        self.assertEqual(data['trace']['decision_id'],self.decision_id)
        self.assertEqual(data['trace']['analysis_id'],self.analysis_id)
        # Employee cannot open development; authorized operational trace still links it.
        session=self.db.get(TrainingSession,entry.session_id)
        from app.training import trace
        chain=trace(self.db,session,self.people['tech'])
        self.assertTrue(chain['development_id']);self.assertEqual(chain['course_version_id'],row.course_version_id)
        evaluation.submit(self.db,row,self.people['employee'],EvaluationSubmit(expected_version=1,answers={
            'application':'YES','problem_persists':'NO','outcome':'RESOLVED'}))
        self.db.expire_all();self.assertEqual(self.db.get(RequestWorkflow,entry.source_request_id).status,'REFERRED')
