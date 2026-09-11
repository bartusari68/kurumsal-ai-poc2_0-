import unittest,json,time
from unittest.mock import patch
from datetime import timedelta
from concurrent.futures import ThreadPoolExecutor
from sqlalchemy import select,update,text,event
from sqlalchemy.exc import IntegrityError
from app.models import RequestRecord,RequestWorkflow,TrainingSession,DevelopmentItem,CourseVersion,CourseCatalog,Enrollment,LearningEvaluation,PortalUser,RequestReferral
from app.portfolio_models import PortfolioItem,PortfolioEvent,PortfolioHandoff,PortfolioLink,install
from app.skill_models import RequestSkillNeed,Skill
from app import portfolio,portfolio_query
from app.portfolio_schemas import ItemCreate,ItemAction
from app.time_policy import utc_now
import test_positions as positions_fixture
import test_skills as skills_fixture
from portfolio_fixtures import seed

class PortfolioTests(positions_fixture.PositionFixture,unittest.TestCase):
    def report(self,skill):
        self.actor=self.people['analyst'];r=self.client.get('/api/portfolio/skills/'+str(skill['id'] if isinstance(skill,dict) else skill.id))
        self.assertEqual(r.status_code,200,r.text);return r.json()

    def item(self,skill=None,**extra):
        skill=skill or self.skill();self.actor=self.people['analyst']
        r=self.client.post('/api/portfolio/items',json={'skill_id':skill['id'] if isinstance(skill,dict) else skill.id,'title':'Synthetic planning topic','rationale':'Review actual evidence',**extra})
        self.assertEqual(r.status_code,201,r.text);return r.json()

    def transition(self,item,action,decision=None,status=200):
        r=self.client.post(f"/api/portfolio/items/{item['id']}/actions",json={'expected_version':item['version'],'action':action,'decision':decision,'note':'Human planning rationale'})
        self.assertEqual(r.status_code,status,r.text);return r.json()

    def decided(self,skill=None,decision='MONITOR'):
        return self.transition(self.transition(self.item(skill),'REVIEW'),'DECIDE',decision)

    def issue(self,item,recipient='employee',target=None,status=201):
        self.actor=self.people['analyst'];r=self.client.post(f"/api/portfolio/items/{item['id']}/handoffs",json={'expected_version':item['version'],'recipient_id':self.people[recipient].user_id,'target_id':target})
        self.assertEqual(r.status_code,status,r.text);return r.json()

    def test_empty_additive_migration_and_idempotent_guards(self):
        install(self.engine);install(self.engine)
        for cls in (PortfolioItem,PortfolioEvent,PortfolioHandoff,PortfolioLink):self.assertEqual(self.count(cls),0)
        self.assertEqual(self.client.get('/api/portfolio').json()['items'],[])

    def test_planned_demand_is_separate_and_real_content_gap(self):
        skill=self.skill();self.profile(skill);r=self.report(skill)
        self.assertEqual((r['planned_profiles'],r['observed_needs']),(1,0))
        self.assertIn('CONTENT_GAP',[s['type'] for s in r['signals']])
        self.assertNotIn('score',json.dumps(r))

    def test_small_demand_does_not_leak_through_signal_or_filters(self):
        skill=self.skill();record,_=self.case();self.need(record,skill);r=self.report(skill)
        self.assertIsNone(r['observed_needs']);self.assertIsNone(r['open_needs'])
        self.assertNotIn('CONTENT_GAP',[s['type'] for s in r['signals']])
        self.assertEqual(self.client.get('/api/portfolio?open_only=true').json()['items'],[])

    def test_batch_counts_no_duplicate_mapping_and_version_outcomes(self):
        data=seed(self.db,self.actor);r=self.report(data['skills'][0])
        self.assertEqual((r['observed_needs'],r['planned_profiles'],r['published_versions']),(10,0,1))
        self.assertTrue(r['last_activity'].endswith('Z'))
        self.assertEqual(r['training']['completions'],10);self.assertEqual(len(r['catalog']),1)
        self.assertEqual(r['catalog'][0]['evaluation_count'],30)
        self.assertEqual(len(r['catalog'][0]['outcomes']),3)
        self.assertTrue(all(o['count']==10 for o in r['catalog'][0]['outcomes']))
        self.assertNotIn('CONTENT_GAP',[s['type'] for s in r['signals']])
        self.assertIn('CONTENT_IMPROVEMENT',[s['type'] for s in r['signals']])

    def test_small_outcomes_are_insufficient_and_no_private_payload(self):
        data=seed(self.db,self.actor,people=4);r=self.report(data['skills'][0]);s=json.dumps(r)
        self.assertNotIn('PRIVATE',s);self.assertNotIn('user_id',s);self.assertNotIn('evaluator_id',s)
        self.assertTrue(all(o['state']=='INSUFFICIENT_DATA' for o in r['catalog'][0]['outcomes']))
        self.assertNotIn('CONTENT_IMPROVEMENT',[s['type'] for s in r['signals']])
        self.assertIsNone(r['catalog'][0]['evaluation_count'])

    def test_complementary_suppression_hides_one_resolved_request(self):
        data=seed(self.db,self.actor);self.db.execute(update(RequestWorkflow).where(RequestWorkflow.request_id==data['requests'][0].id).values(status='RESOLVED'));self.db.commit()
        r=self.report(data['skills'][0]);self.assertIsNone(r['observed_needs']);self.assertIsNone(r['open_needs']);self.assertIsNone(r['resolved_needs']);self.assertIsNone(r['repeated_needs'])

    def test_repeated_need_requires_same_user_and_strict_after_completion(self):
        data=seed(self.db,self.actor);r=self.report(data['skills'][0]);self.assertEqual(r['repeated_needs'],10)
        self.db.execute(update(RequestRecord).values(created_at=utc_now()-timedelta(days=10)));self.db.commit()
        self.assertEqual(self.report(data['skills'][0])['repeated_needs'],0)

    def test_removed_completion_and_stale_evaluation_excluded(self):
        data=seed(self.db,self.actor)
        self.db.execute(update(Enrollment).values(completed_at=utc_now()));self.db.commit()
        r=self.report(data['skills'][0]);self.assertEqual(r['catalog'][0]['outcomes'],[]);self.assertEqual(r['catalog'][0]['evaluation_count'],0)
        self.db.execute(update(Enrollment).values(status='REMOVED'));self.db.commit()
        self.assertEqual(self.report(data['skills'][0])['training']['completions'],0)

    def test_capacity_signal_uses_actual_future_scheduled_session(self):
        data=seed(self.db,self.actor);r=self.report(data['skills'][0]);self.assertIn('CAPACITY_SIGNAL',[s['type'] for s in r['signals']])
        self.db.add(TrainingSession(course_version_id=data['version'].id,title='Upcoming',responsible_unit='TECHNICAL_DESIGN',delivery_mode='ONLINE',status='SCHEDULED',start_at=utc_now()+timedelta(days=2),end_at=utc_now()+timedelta(days=3),capacity=20,created_by=self.actor.user_id));self.db.commit()
        r=self.report(data['skills'][0]);self.assertEqual(r['training']['upcoming_capacity'],20);self.assertNotIn('CAPACITY_SIGNAL',[s['type'] for s in r['signals']])

    def test_healthy_coverage_requires_actual_current_positive_results_and_no_open_need(self):
        data=seed(self.db,self.actor,outcome='RESOLVED',progress='CLEAR',repeat=False)
        self.db.execute(update(RequestWorkflow).values(status='RESOLVED'));self.db.commit()
        r=self.report(data['skills'][0]);self.assertIn('HEALTHY_COVERAGE',[s['type'] for s in r['signals']])
        self.assertNotIn('INSUFFICIENT_DATA',[s['type'] for s in r['signals']])

    def test_concurrent_creations_keep_one_active_topic(self):
        skill=self.skill();actor=self.people['analyst']
        def create_one(_):
            from fastapi import HTTPException
            with self.factory() as db:
                try:portfolio.create(db,actor,ItemCreate(skill_id=skill['id'],title='Concurrent topic',rationale='Human rationale'));return 201
                except HTTPException as e:return e.status_code
        with ThreadPoolExecutor(max_workers=2) as pool:codes=list(pool.map(create_one,range(2)))
        self.assertEqual(sorted(codes),[201,409]);self.assertEqual(self.count(PortfolioItem),1)

    def test_anonymous_portfolio_and_handoffs_denied(self):
        from app.main import app
        from app.portal_auth import current_account
        app.dependency_overrides[current_account]=lambda:None
        for url in ('/api/portfolio','/api/portfolio/handoffs','/api/portfolio/items','/api/portfolio/items/1'):
            self.assertEqual(self.client.get(url).status_code,401)

    def test_item_snapshot_and_decision_preserve_evidence_as_it_was(self):
        skill=self.skill();item=self.item(skill);self.profile(skill);item=self.transition(item,'REVIEW');item=self.transition(item,'DECIDE','MONITOR')
        self.assertEqual(item['history'][0]['snapshot']['planned_profiles'],0)
        self.assertEqual(item['history'][-1]['snapshot']['planned_profiles'],1)
        for sql in ("UPDATE portfolio_events SET snapshot_json='{}'",'DELETE FROM portfolio_events',"UPDATE portfolio_items SET decision='NO_ACTION'",'DELETE FROM portfolio_items'):
            with self.assertRaises(IntegrityError):self.db.execute(text(sql));self.db.commit()
            self.db.rollback()

    def test_active_duplicate_conflict_and_new_item_after_close(self):
        skill=self.skill();item=self.decided(skill);self.actor=self.people['analyst']
        r=self.client.post('/api/portfolio/items',json={'skill_id':skill['id'],'title':'Duplicate','rationale':'Duplicate context'})
        self.assertEqual(r.status_code,409);self.transition(item,'CLOSE');self.item(skill)

    def test_invalid_transition_stale_version_and_assignee(self):
        item=self.item(assignee_id=self.people['analyst'].user_id);self.transition(item,'CLOSE',status=422)
        self.transition(item,'REVIEW');self.transition(item,'REVIEW',status=409)
        self.actor=self.people['analyst2'];self.transition({**item,'version':2},'DECIDE','NO_ACTION',status=403)

    def test_decision_does_not_create_any_downstream(self):
        before=[self.count(m) for m in (RequestRecord,DevelopmentItem,TrainingSession)]
        self.decided(decision='CREATE_NEW_LEARNING_NEED')
        self.assertEqual(before,[self.count(m) for m in (RequestRecord,DevelopmentItem,TrainingSession)])

    def test_explicit_request_handoff_existing_pipeline_atomic_trace_and_retry(self):
        item=self.decided(decision='CREATE_NEW_LEARNING_NEED');handoff=self.issue(item)
        self.assertEqual(self.count(RequestRecord),0);self.actor=self.people['employee']
        self.assertEqual(self.client.get(f"/api/portfolio/handoffs/{handoff['id']}").status_code,200)
        payload={'text':'Synthetic actual need context','idempotency_key':'portfolio-stable','portfolio_handoff_id':handoff['id']}
        r=self.client.post('/api/requests/analyze',json=payload);self.assertEqual(r.status_code,202,r.text)
        again=self.client.post('/api/requests/analyze',json=payload);self.assertEqual(again.json()['request_id'],r.json()['request_id'])
        self.assertEqual(self.count(PortfolioLink),1);self.assertEqual(self.count(RequestRecord),1)
        self.assertEqual(self.client.post('/api/requests/analyze',json={**payload,'portfolio_handoff_id':None}).status_code,409)
        self.assertEqual(self.client.post('/api/requests/analyze',json={**payload,'idempotency_key':'another-key'}).status_code,409)
        self.assertEqual(self.count(RequestRecord),1)
        self.actor=self.people['analyst'];trace=self.client.get(f"/api/portfolio/items/{item['id']}").json()['handoffs'][0]
        self.assertEqual(trace['link']['request_id'],r.json()['request_id']);self.assertTrue(trace['decision_event_id'])

    def test_recipient_scope_and_closed_handoff_rollback(self):
        item=self.decided(decision='CREATE_NEW_LEARNING_NEED');h=self.issue(item)
        self.actor=self.people['employee2'];self.assertEqual(self.client.get('/api/portfolio/handoffs').json()['items'],[])
        self.assertEqual(self.client.get(f"/api/portfolio/handoffs/{h['id']}").status_code,404)
        self.actor=self.people['analyst'];self.transition(item,'CLOSE');self.actor=self.people['employee']
        r=self.client.post('/api/requests/analyze',json={'text':'Synthetic closed source','portfolio_handoff_id':h['id']})
        self.assertEqual(r.status_code,409);self.assertEqual(self.count(RequestRecord),0)

    def test_report_and_snapshot_scope_is_needs_analyst_only(self):
        item=self.item()
        for role in ('employee','tech','engineering'):
            self.actor=self.people[role]
            for url in ('/api/portfolio',f"/api/portfolio/skills/{item['skill_id']}",'/api/portfolio/items',f"/api/portfolio/items/{item['id']}",'/api/portfolio/options'):
                self.assertEqual(self.client.get(url).status_code,403,url)

    def test_handoff_duplicate_is_idempotent(self):
        item=self.decided(decision='CREATE_NEW_LEARNING_NEED');a=self.issue(item);b=self.issue(item)
        self.assertEqual(a['id'],b['id']);self.assertEqual(self.count(PortfolioHandoff),1)

    def test_explicit_session_handoff_reuses_training_creation(self):
        data=seed(self.db,self.actor);item=self.decided(data['skills'][0],decision='PLAN_ADDITIONAL_SESSIONS')
        h=self.issue(item,recipient='tech',target=data['version'].id);before=self.count(TrainingSession)
        self.actor=self.people['tech'];payload={'course_version_id':data['version'].id,'responsible_unit':'TECHNICAL_DESIGN','delivery_mode':'ONLINE','portfolio_handoff_id':h['id']}
        r=self.client.post('/api/training',json=payload);self.assertEqual(r.status_code,201,r.text)
        self.assertEqual(self.count(TrainingSession),before+1);self.assertEqual(self.db.scalar(select(PortfolioLink)).session_id,r.json()['id'])
        self.assertEqual(self.client.post('/api/training',json=payload).status_code,409);self.assertEqual(self.count(TrainingSession),before+1)

    def test_handoff_rejects_wrong_role_and_unmapped_course(self):
        data=seed(self.db,self.actor);item=self.decided(data['skills'][0],decision='PLAN_ADDITIONAL_SESSIONS')
        self.issue(item,recipient='engineering',target=data['version'].id,status=403)
        self.issue(item,recipient='tech',target=999,status=422);self.assertEqual(self.count(PortfolioHandoff),0)

    def test_one_thousand_relationships_query_count_is_constant(self):
        seed(self.db,self.actor,people=1000,skill_count=1)
        sql=[]
        def collect(*args):sql.append(args[2])
        event.listen(self.engine,'before_cursor_execute',collect)
        started=time.perf_counter();data=portfolio_query.aggregate(self.db,self.actor);elapsed=time.perf_counter()-started
        first=len(sql);self.assertEqual(data['items'][0]['observed_needs'],1000);self.assertEqual(data['items'][0]['catalog'][0]['evaluation_count'],3000)
        event.remove(self.engine,'before_cursor_execute',collect)
        seed(self.db,self.actor,people=5,skill_count=12);sql.clear();event.listen(self.engine,'before_cursor_execute',collect)
        portfolio_query.aggregate(self.db,self.actor);event.remove(self.engine,'before_cursor_execute',collect)
        self.assertEqual(len(sql),first);self.assertLessEqual(first,15);self.assertLess(elapsed,10)
        print(f'Portfolio benchmark: 1000 requests + 1000 enrollments + 3000 evaluations, {first} SQL, {elapsed:.3f}s',flush=True)

class PortfolioLifecycleTests(skills_fixture.SkillFixture,unittest.TestCase):
    for _name in ('source','create','edit_payload','edit','action','ready','finish','draft','metadata','publish_action','published','mapped','live_version'):
        locals()[_name]=getattr(skills_fixture.SkillLifecycleTests,_name)
    item=PortfolioTests.item
    transition=PortfolioTests.transition
    decided=PortfolioTests.decided
    issue=PortfolioTests.issue
    report=PortfolioTests.report

    def test_version_one_and_two_results_do_not_mix(self):
        data=seed(self.db,self.actor);old=data['version'];self.db.execute(update(CourseVersion).where(CourseVersion.id==old.id).values(state='ARCHIVED',revision=CourseVersion.revision+1));self.db.commit()
        # Real source version 2 begins as a legacy draft with its own immutable mappings.
        from app.skill_models import CourseSkillMapping
        v=CourseVersion(course_id=old.course_id,version_number=2,title='New version',state='DRAFT',legacy=True)
        self.db.add(v);self.db.flush();self.db.add(CourseSkillMapping(course_version_id=v.id,skill_id=data['skills'][0].id,created_by=self.actor.user_id));self.db.flush();v.state='PUBLISHED';self.db.flush()
        self.db.execute(update(CourseCatalog).where(CourseCatalog.course_id==old.course_id).values(current_version_id=v.id));self.db.commit()
        r=self.report(data['skills'][0]);versions={x['version_number']:x for x in r['catalog']}
        self.assertEqual(versions[1]['evaluation_count'],30);self.assertEqual(versions[2]['evaluation_count'],0)
        self.assertTrue(all(s['course_version_id']==old.id for s in r['signals'] if s['type']=='CONTENT_IMPROVEMENT'))
        self.assertNotIn('HEALTHY_COVERAGE',[s['type'] for s in r['signals']])
        self.assertIn('INSUFFICIENT_DATA',[s['type'] for s in r['signals']])

    def test_enrichment_handoff_preserves_existing_request_authority(self):
        import test_development as development_fixture
        record,flow,payload=development_fixture.DevelopmentTests.source(self,enrichment=True)
        skill=self.skill();self.need(record,skill)
        item=self.decided(skill,decision='START_COURSE_ENRICHMENT');h=self.issue(item,'tech',record.id)
        self.assertEqual(self.count(DevelopmentItem),0);self.actor=self.people['tech']
        r=self.client.post('/api/development',json={**payload,'portfolio_handoff_id':h['id']})
        self.assertEqual(r.status_code,201,r.text);self.assertEqual(self.count(DevelopmentItem),1)
        self.assertEqual(self.db.scalar(select(PortfolioLink)).development_id,r.json()['id'])
        self.db.execute(update(RequestReferral).values(active=False));self.db.commit()
        self.assertEqual(self.client.get(f"/api/portfolio/handoffs/{h['id']}").status_code,404)
        visible=self.client.get('/api/portfolio/handoffs').json()['items'][0]
        self.assertIsNone(visible['link']);self.assertNotIn('source_request_id',visible['context'])
