import unittest,json
from concurrent.futures import ThreadPoolExecutor
from sqlalchemy import select,update,text
from sqlalchemy.exc import IntegrityError
import test_operations as ops
import test_publishing as pub
import test_evaluation as evaluation_fixtures
from app import skills,skill_evidence,skill_reporting
from app.skill_models import Skill,SkillGroup,SkillTerm,CourseSkillMapping,RequestSkillNeed,SkillEvidence,SkillAudit,install
from app.models import CourseVersion,CourseCatalog,Enrollment,LearningEvaluation,RequestWorkflow,AnalysisRun,DevelopmentItem,PortalUser,RequestReferral
from app.skill_schemas import SkillWrite
from app.time_policy import utc_now


class SkillFixture:
    tearDown=ops.OperationsTests.tearDown
    case=ops.OperationsTests.case
    count=ops.OperationsTests.count
    delegate=ops.OperationsTests.delegate

    def setUp(self):
        ops.OperationsTests.setUp(self);install(self.engine,self.factory)

    def skill(self,name='Python',aliases=None,status=201):
        previous=self.actor;self.actor=self.people['analyst']
        response=self.client.post('/api/skills',json={'canonical_name':name,'description':'Synthetic skill','group_id':self.db.scalar(select(SkillGroup.id).where(SkillGroup.code=='SOFTWARE')),'aliases':aliases or []})
        self.assertEqual(response.status_code,status,response.text);self.actor=previous;return response.json()

    def need(self,record,skill,source='MANUAL',**extra):
        previous=self.actor;self.actor=self.people['analyst']
        response=self.client.post(f'/api/skills/requests/{record.id}',json={'skill_id':skill['id'],'source':source,**extra})
        self.assertEqual(response.status_code,201,response.text);self.actor=previous;return response.json()

    def candidate(self,record,flow):
        run=AnalysisRun(request_id=record.id,sequence=1,status='COMPLETED',trigger='IMPORTED',input_json='{}',result_json=json.dumps({'classification':{'requirements':[{'id':'N1','label':'Python Programming ile veri işlemek'},{'id':'N2','label':'Tanımlanmamış yeni konu'}]}}))
        self.db.add(run);self.db.commit();return run


class SkillTests(SkillFixture,unittest.TestCase):
    def test_group_seed_reuses_classification_without_creating_skills(self):
        self.assertEqual(self.count(SkillGroup),11);install(self.engine,self.factory)
        self.assertEqual(self.count(SkillGroup),11);self.assertEqual(self.count(Skill),0)

    def test_canonical_and_alias_normalization(self):
        row=self.skill('Python',['Python Programming','Python geliştirme'])
        self.assertEqual(len(row['aliases']),2)
        for query in ('PYTHON','python programming','Python   geliştirme'):
            self.assertEqual(self.client.get('/api/skills',params={'search':query}).json()['items'][0]['id'],row['id'])
        self.assertEqual(skills.normalize('İŞ  TESTİ'),skills.normalize('iş testi'))

    def test_duplicate_name_and_cross_alias_collisions(self):
        self.skill('Python',['Python Programming']);self.skill(' python ',status=409)
        self.skill('Python Programming',status=409);self.skill('Other',['PYTHON'],status=409)
        self.assertEqual(self.count(Skill),1)

    def test_concurrent_canonical_collision(self):
        group=self.db.scalar(select(SkillGroup.id));actor=self.people['analyst']
        def create():
            from fastapi import HTTPException
            with self.factory() as db:
                try:skills.write_skill(db,actor,SkillWrite(canonical_name='Concurrent',group_id=group));return 201
                except HTTPException as error:return error.status_code
        with ThreadPoolExecutor(max_workers=2) as pool:codes=list(pool.map(lambda _:create(),range(2)))
        self.assertEqual(sorted(codes),[201,409])

    def test_edit_rename_and_deactivate_preserve_terms_history(self):
        row=self.skill();payload={'canonical_name':'Python geliştirme','description':'Changed','group_id':row['group_id'],'aliases':['Python Programming'],'status':'INACTIVE','expected_version':row['version']}
        result=self.client.patch(f"/api/skills/{row['id']}",json=payload);self.assertEqual(result.status_code,200,result.text)
        self.assertIn('Python',result.json()['aliases']);self.assertEqual(self.client.get('/api/skills/options').json()['items'],[])
        self.assertEqual(self.client.patch(f"/api/skills/{row['id']}",json=payload).status_code,409)
        with self.assertRaises(IntegrityError):self.db.execute(text('DELETE FROM skills'));self.db.commit()
        self.db.rollback()

    def test_only_steward_manages_global_vocabulary(self):
        row=self.skill()
        for name in ('employee','tech','engineering'):
            self.actor=self.people[name]
            self.assertEqual(self.client.post('/api/skills',json={'canonical_name':'Other','group_id':row['group_id']}).status_code,403)
        self.actor=self.people['employee'];self.assertEqual(self.client.get('/api/skills').status_code,403)

    def test_suggested_and_confirmed_are_separate_and_no_auto_skill(self):
        skill=self.skill(aliases=['Python Programming']);record,flow=self.case();run=self.candidate(record,flow)
        data=self.client.get(f'/api/skills/requests/{record.id}').json()
        self.assertEqual(len(data['candidates']),1);self.assertEqual(data['unmapped_needs'],['Tanımlanmamış yeni konu']);self.assertEqual(self.count(Skill),1)
        need=self.need(record,skill,'AI_SUGGESTED',analysis_run_id=run.id)
        self.assertFalse(need['human_verified']);self.assertEqual(self.count(SkillEvidence),0)
        result=self.client.post(f"/api/skills/requests/{record.id}/{need['id']}",json={'action':'CONFIRM','expected_version':1})
        self.assertEqual(result.status_code,200,result.text)
        self.db.expire_all();row=self.db.get(RequestSkillNeed,need['id']);self.assertEqual(row.source,'HUMAN_CONFIRMED');self.assertTrue(row.human_verified)
        self.assertEqual(self.count(SkillEvidence),1);self.assertEqual(self.db.get(RequestWorkflow,record.id).status,'IN_REVIEW')

    def test_one_action_candidate_confirmation_keeps_ai_provenance(self):
        skill=self.skill();record,flow=self.case();run=self.candidate(record,flow)
        row=self.need(record,skill,'AI_SUGGESTED',analysis_run_id=run.id,confirm=True)
        self.assertEqual(row['source'],'HUMAN_CONFIRMED');self.assertEqual(row['provenance']['origin'],'AI_SUGGESTED')

    def test_no_fuzzy_match_or_uncontrolled_skill(self):
        self.skill('Python');record,flow=self.case();flow.result_json=json.dumps({'classification':{'requirements':[{'label':'Pythonesque tools'}]}});self.db.commit()
        data=skills.candidate_data(self.db,record,flow);self.assertEqual(data['candidates'],[]);self.assertEqual(self.count(Skill),1)

    def test_dismissed_candidate_does_not_return_or_generate_evidence(self):
        skill=self.skill();record,flow=self.case();run=self.candidate(record,flow)
        row=self.need(record,skill,'AI_SUGGESTED',analysis_run_id=run.id,dismiss=True)
        repeated=self.need(record,skill,'AI_SUGGESTED',analysis_run_id=run.id,dismiss=True)
        self.assertEqual(row['id'],repeated['id']);self.assertFalse(row['active']);self.assertFalse(row['human_verified'])
        section=self.client.get(f'/api/skills/requests/{record.id}').json()
        self.assertEqual(section['candidates'],[]);self.assertEqual(len(section['items']),1);self.assertEqual(self.count(SkillEvidence),0)
        self.need(record,skill);self.assertEqual(self.count(SkillEvidence),1)

    def test_dismissal_cannot_be_combined_with_confirmation(self):
        skill=self.skill();record,flow=self.case()
        for payload in ({'source':'MANUAL','dismiss':True},{'source':'AI_SUGGESTED','dismiss':True,'confirm':True}):
            response=self.client.post(f'/api/skills/requests/{record.id}',json={'skill_id':skill['id'],**payload})
            self.assertEqual(response.status_code,422)
        self.assertEqual(self.count(RequestSkillNeed),0)

    def test_stale_or_forged_candidate_rejected(self):
        skill=self.skill();record,flow=self.case();run=self.candidate(record,flow)
        result=self.client.post(f'/api/skills/requests/{record.id}',json={'skill_id':skill['id'],'source':'AI_SUGGESTED','analysis_run_id':999})
        self.assertEqual(result.status_code,409)
        need=self.need(record,skill,'AI_SUGGESTED',analysis_run_id=run.id)
        self.db.add(AnalysisRun(request_id=record.id,sequence=2,status='PENDING',active_request_id=record.id,trigger='MANUAL',input_json='{}'));self.db.commit()
        self.assertEqual(self.client.post(f"/api/skills/requests/{record.id}/{need['id']}",json={'action':'CONFIRM','expected_version':1}).status_code,409)

    def test_replace_withdraw_audit_and_evidence_are_historical(self):
        first=self.skill();second=self.skill('SQL');record,flow=self.case();need=self.need(record,first)
        self.assertEqual(self.count(SkillEvidence),1)
        result=self.client.post(f"/api/skills/requests/{record.id}/{need['id']}",json={'action':'REPLACE','expected_version':1,'replacement_skill_id':second['id']})
        self.assertEqual(result.status_code,200,result.text);self.assertEqual(self.count(SkillEvidence),2)
        self.db.expire_all();self.assertFalse(self.db.get(RequestSkillNeed,need['id']).active)
        self.actor=self.people['employee'];profile=self.client.get(f"/api/skills/mine/{first['id']}").json()
        self.assertFalse(profile['evidence']['items'][0]['source_current'])
        with self.assertRaises(IntegrityError):self.db.execute(text('UPDATE skill_evidence SET signal=\'changed\''));self.db.commit()
        self.db.rollback()

    def test_inactive_skill_cannot_enter_new_need(self):
        skill=self.skill();self.db.execute(update(Skill).values(status='INACTIVE'));self.db.commit();record,flow=self.case()
        self.assertEqual(self.client.post(f'/api/skills/requests/{record.id}',json={'skill_id':skill['id']}).status_code,422)

    def test_duplicate_manual_processing_one_need_one_evidence(self):
        skill=self.skill();record,flow=self.case();first=self.need(record,skill);second=self.need(record,skill)
        self.assertEqual(first['id'],second['id']);skill_evidence.from_need(self.db,self.db.get(RequestSkillNeed,first['id']),flow);self.db.commit()
        self.assertEqual(self.count(SkillEvidence),1)

    def test_scope_and_profile_privacy(self):
        skill=self.skill();record,flow=self.case('REFERRED','TECHNICAL_DESIGN');self.need(record,skill)
        self.actor=self.people['employee2'];self.assertEqual(self.client.get(f"/api/skills/mine/{skill['id']}").status_code,404)
        self.assertEqual(self.client.get('/api/skills/mine?user_id='+str(self.people['employee'].user_id)).json()['total'],0)
        self.actor=self.people['engineering'];data=self.client.get(f"/api/skills/{skill['id']}").json()
        self.assertEqual(data['confirmed_demand'],0);self.assertEqual(data['evidence_count'],0);self.assertEqual(data['requests'],[])
        self.assertEqual(self.client.get(f'/api/skills/requests/{record.id}').status_code,404)
        self.actor=self.people['tech'];data=self.client.get('/api/skills').json()['items'][0]
        self.assertEqual(data['confirmed_demand'],1);self.assertNotIn('user_id',data);self.assertNotIn('employee',str(data))

    def test_no_fake_levels_and_gap_signal_without_completion(self):
        skill=self.skill();record,flow=self.case();self.need(record,skill);self.actor=self.people['employee']
        data=self.client.get('/api/skills/mine').json()['items'][0]
        self.assertEqual(data['evidence_count'],1);self.assertTrue(data['need_signals'])
        for key in ('score','proficiency','level','rank','percentage'):self.assertNotIn(key,data)

    def test_anonymous_routes_denied(self):
        from app.main import app
        from app.portal_auth import current_account
        app.dependency_overrides[current_account]=lambda:None
        for url in ('/api/skills','/api/skills/mine','/api/skills/options','/api/skills/1'):
            self.assertEqual(self.client.get(url).status_code,401)


class SkillLifecycleTests(SkillFixture,unittest.TestCase):
    for _name in ('source','create','edit_payload','edit','action','ready','finish','draft','metadata','publish_action','published'):
        locals()[_name]=getattr(evaluation_fixtures.EvaluationTraceTests,_name)

    def mapped(self):
        skill=self.skill();version,dev,record,flow,payload=self.draft();self.need(record,skill)
        response=self.client.put(f"/api/skills/versions/{version['id']}",json={'expected_version':version['revision'],
            'mappings':[{'skill_id':skill['id'],'outcome_index':0},{'skill_id':skill['id'],'outcome_index':-1}]})
        self.assertEqual(response.status_code,200,response.text)
        return skill,response.json(),dev,record,flow

    def live_version(self):
        skill,version,dev,record,flow=self.mapped();version=self.metadata(version);version=self.publish_action(version,'PREPARE');version=self.publish_action(version,'PUBLISH')
        return skill,version,dev,record,flow

    def train(self,version,record=None):
        self.actor=self.people['tech']
        r=self.client.post('/api/training',json={'course_version_id':version['id'],'responsible_unit':'TECHNICAL_DESIGN','delivery_mode':'ONLINE','external_trainer':'Synthetic trainer','online_url':'https://example.com/training','start_at':'2026-10-01T10:00:00Z','end_at':'2026-10-01T12:00:00Z'})
        self.assertEqual(r.status_code,201,r.text);row=r.json()
        row=self.client.post(f"/api/training/{row['id']}/enrollments",json={'expected_version':row['version'],'user_id':self.people['employee'].user_id,'source_request_id':record.id if record else None}).json()
        for action in ('SCHEDULE','START'):row=self.client.post(f"/api/training/{row['id']}/actions",json={'expected_version':row['version'],'action':action}).json()
        e=row['enrollments'][0]
        r=self.client.post(f"/api/training/{row['id']}/completion",json={'expected_version':row['version'],'rows':[{'id':e['id'],'version':e['version'],'completion':'COMPLETED'}]})
        self.assertEqual(r.status_code,200,r.text);return r.json()

    def evaluate(self,session,kind='LEARNING',source='PARTICIPANT'):
        self.actor=self.people['tech']
        if kind=='APPLICATION':
            response=self.client.post('/api/evaluations',json={'enrollment_id':session['enrollments'][0]['id'],'evaluation_type':kind,'evaluator_source':source,'evaluator_id':self.people['tech'].user_id if source=='AUTHORIZED_REVIEWER' else None});self.assertEqual(response.status_code,201,response.text)
        self.db.expire_all();row=self.db.scalar(select(LearningEvaluation).where(LearningEvaluation.enrollment_id==session['enrollments'][0]['id'],LearningEvaluation.evaluation_type==kind,LearningEvaluation.evaluator_source==source))
        self.actor=self.people['tech'] if source=='AUTHORIZED_REVIEWER' else self.people['employee']
        data=self.client.get(f'/api/evaluations/{row.id}').json();answers={}
        for q in data['template']['questions']:
            if q['type']=='free_text':answers[q['id']]='PRIVATE feedback'
            elif q['type']=='rating':answers[q['id']]=4
            elif q['id']=='outcome':answers[q['id']]='PARTIALLY_RESOLVED'
            else:answers[q['id']]=next(iter(q['options']))
        response=self.client.post(f'/api/evaluations/{row.id}/submit',json={'expected_version':1,'answers':answers});self.assertEqual(response.status_code,200,response.text)
        return row

    def test_mapping_course_outcome_and_snapshot_immutable(self):
        skill,version,dev,record,flow=self.live_version();self.assertEqual(len(version['skills']),2)
        response=self.client.put(f"/api/skills/versions/{version['id']}",json={'expected_version':version['revision'],'mappings':[]})
        self.assertIn(response.status_code,(403,422));before=self.count(CourseSkillMapping)
        with self.assertRaises(IntegrityError):self.db.execute(text('DELETE FROM course_skill_mappings'));self.db.commit()
        self.db.rollback();self.assertEqual(self.count(CourseSkillMapping),before)

    def test_invalid_outcome_duplicate_stale_mapping_and_scope(self):
        skill,version,dev,record,flow=self.mapped()
        for entries,status,revision in [([{'skill_id':skill['id'],'outcome_index':99}],422,version['revision']),
            ([{'skill_id':skill['id']},{'skill_id':skill['id']}],422,version['revision']),([],409,1)]:
            response=self.client.put(f"/api/skills/versions/{version['id']}",json={'expected_version':revision,'mappings':entries});self.assertEqual(response.status_code,status,response.text)
        self.actor=self.people['engineering'];self.assertEqual(self.client.put(f"/api/skills/versions/{version['id']}",json={'expected_version':version['revision'],'mappings':[]}).status_code,404)

    def test_inactive_mapping_rejected_without_losing_old_rows(self):
        skill,version,dev,record,flow=self.mapped();self.db.execute(update(Skill).values(status='INACTIVE'));self.db.commit()
        response=self.client.put(f"/api/skills/versions/{version['id']}",json={'expected_version':version['revision'],'mappings':[{'skill_id':skill['id']}]})
        self.assertEqual(response.status_code,422);self.assertEqual(self.count(CourseSkillMapping),2)

    def test_completion_and_evaluation_evidence_idempotent(self):
        skill,version,dev,record,flow=self.live_version();session=self.train(version,record);evaluation=self.evaluate(session)
        self.db.expire_all();entry=self.db.get(Enrollment,session['enrollments'][0]['id']);evaluation=self.db.get(LearningEvaluation,evaluation.id)
        before=self.count(SkillEvidence);skill_evidence.from_completion(self.db,entry);skill_evidence.from_evaluation(self.db,evaluation);self.db.commit()
        self.assertEqual(self.count(SkillEvidence),before)
        types=list(self.db.scalars(select(SkillEvidence.evidence_type)));self.assertCountEqual(types,['REQUEST_NEED','TRAINING_COMPLETION','SELF_EVALUATION'])

    def test_full_trace_and_no_request_closure(self):
        skill,version,dev,record,flow=self.live_version();session=self.train(version,record);evaluation=self.evaluate(session,'APPLICATION')
        self.actor=self.people['employee'];data=self.client.get(f"/api/skills/mine/{skill['id']}").json()
        evidence=next(e for e in data['evidence']['items'] if e['type']=='OUTCOME_EVALUATION');trace=evidence['trace']
        self.assertEqual(trace['need_request_id'],record.id);self.assertEqual(trace['analysis_id'],self.analysis_id)
        self.assertEqual(trace['decision_id'],self.decision_id);self.assertEqual(trace['evaluation_id'],evaluation.id)
        self.assertEqual(trace['course_version_id'],version['id']);self.assertEqual(trace['session_id'],session['id'])
        self.assertNotIn('PRIVATE feedback',json.dumps(data));self.db.expire_all();self.assertEqual(self.db.get(RequestWorkflow,record.id).status,'REFERRED')

    def test_authorized_evidence_belongs_to_participant_and_hides_private_response(self):
        skill,version,dev,record,flow=self.live_version();session=self.train(version,record);self.evaluate(session,'APPLICATION','AUTHORIZED_REVIEWER')
        self.actor=self.people['employee'];data=self.client.get(f"/api/skills/mine/{skill['id']}").json()
        evidence=next(e for e in data['evidence']['items'] if e['type']=='AUTHORIZED_VALIDATION')
        self.assertFalse(evidence['trace']['can_open_evaluation']);self.assertEqual(evidence['signal'],'PARTIALLY_RESOLVED')
        self.assertNotIn('PRIVATE feedback',json.dumps(data))

    def test_demand_coverage_and_outcome_reporting_no_automatic_development(self):
        skill,version,dev,record,flow=self.live_version();session=self.train(version,record);self.evaluate(session,'APPLICATION')
        self.actor=self.people['tech'];before=self.count(DevelopmentItem);data=self.client.get(f"/api/skills/{skill['id']}").json()
        self.assertEqual(data['published_version_count'],1);self.assertEqual(data['active_demand'],1)
        self.assertEqual(data['outcomes'][0]['outcome'],'PARTIALLY_RESOLVED');self.assertTrue(data['signals']);self.assertEqual(self.count(DevelopmentItem),before)
        self.actor=self.people['engineering'];data=self.client.get(f"/api/skills/{skill['id']}").json();self.assertEqual(data['outcomes'],[])

    def test_repeated_outcomes_link_existing_content_improvement_to_skill(self):
        skill,version,dev,record,flow=self.live_version()
        for _ in range(2):self.evaluate(self.train(version,record),'APPLICATION')
        self.actor=self.people['tech'];data=self.client.get(f"/api/skills/{skill['id']}").json()
        signal=next(s for s in data['content_improvement_signals'] if s['kind']=='UNMET_NEED')
        self.assertEqual(signal['count'],2);self.assertEqual(signal['course_version_id'],version['id'])
        self.actor=self.people['employee'];profile=self.client.get(f"/api/skills/mine/{skill['id']}").json()
        self.assertTrue(any('sonuç değerlendirmesinde' in s for s in profile['need_signals']))
        self.actor=self.people['engineering'];self.assertEqual(self.client.get(f"/api/skills/{skill['id']}").json()['content_improvement_signals'],[])

    def test_completion_correction_retains_historical_evidence(self):
        skill,version,dev,record,flow=self.live_version();session=self.train(version,record)
        self.db.execute(update(Enrollment).values(completion='NOT_COMPLETED',completed_at=None));self.db.commit()
        self.actor=self.people['employee'];data=self.client.get(f"/api/skills/mine/{skill['id']}").json()
        evidence=next(e for e in data['evidence']['items'] if e['type']=='TRAINING_COMPLETION');self.assertFalse(evidence['source_current'])

    def test_new_version_does_not_rewrite_old_mapping_or_evidence(self):
        skill,version,dev,record,flow=self.live_version();session=self.train(version,record)
        other=self.skill('SQL')
        old=self.db.get(CourseVersion,version['id']);old.state='ARCHIVED';old.revision+=1;self.db.flush()
        second=CourseVersion(course_id=old.course_id,version_number=2,title='New version',state='DRAFT',outcomes_json='[{"text":"New outcome"}]')
        self.db.add(second);self.db.flush()
        self.db.add(CourseSkillMapping(course_version_id=second.id,skill_id=other['id'],outcome_index=0,outcome_text='New outcome',created_by=self.people['tech'].user_id));self.db.flush()
        second.state='PUBLISHED';self.db.flush();self.db.get(CourseCatalog,old.course_id).current_version_id=second.id;self.db.commit()
        self.train({'id':second.id})
        old_ev=self.db.scalar(select(SkillEvidence).where(SkillEvidence.evidence_type=='TRAINING_COMPLETION',SkillEvidence.course_version_id==old.id))
        new_ev=self.db.scalar(select(SkillEvidence).where(SkillEvidence.evidence_type=='TRAINING_COMPLETION',SkillEvidence.course_version_id==second.id))
        self.assertEqual(old_ev.skill_id,skill['id']);self.assertEqual(new_ev.skill_id,other['id'])
