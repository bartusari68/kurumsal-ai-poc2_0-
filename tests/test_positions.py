import unittest, json
from sqlalchemy import select, update, text
from sqlalchemy.exc import IntegrityError
from app.models import PortalUser, RequestRecord, RequestWorkflow, AnalysisRun, CourseVersion
from app.position_models import PositionProfile, PositionRevision, PositionRequirement, UserPosition, PositionAudit, RequestPositionSource
from app.skill_models import Skill, SkillEvidence
from app import positions, position_gap
import test_skills as skill_fixtures
SkillFixture=skill_fixtures.SkillFixture

class PositionFixture(SkillFixture):
    def profile(self, skill=None, name='Sentetik pozisyon', **extra):
        self.actor=self.people['analyst']
        payload={'name':name,'requirements':[{'skill_id':skill['id'],'rationale':'Sentetik görev gereksinimi'}] if skill else [],**extra}
        r=self.client.post('/api/positions',json=payload);self.assertEqual(r.status_code,201,r.text);return r.json()

    def assign(self, profile, person='employee', expected=0):
        self.actor=self.people['analyst'];r=self.client.put('/api/positions/users/'+str(self.people[person].user_id),json={'profile_id':profile['id'] if profile else None,'expected_version':expected})
        self.assertEqual(r.status_code,200,r.text);return r.json()

    def edit(self, profile, **extra):
        self.actor=self.people['analyst']
        payload={k:profile[k] for k in ('name','code','description','organization','unit','status')}
        payload.update(expected_version=profile['version'],requirements=[{k:r[k] for k in ('skill_id','requirement_type','rationale')} for r in profile['requirements']]);payload.update(extra)
        response=self.client.put('/api/positions/'+str(profile['id']),json=payload)
        self.assertEqual(response.status_code,200,response.text);return response.json()

class PositionTests(PositionFixture,unittest.TestCase):
    def test_empty_migration_has_no_fake_profiles_or_assignments(self):
        self.assertEqual(self.count(PositionProfile),0);self.assertEqual(self.count(UserPosition),0)
        self.actor=self.people['employee'];self.assertFalse(self.client.get('/api/positions/mine').json()['assigned'])

    def test_create_profile_requirements_and_source_names(self):
        skill=self.skill();row=self.profile(skill)
        self.assertEqual(row['version'],1);self.assertEqual(row['requirements'][0]['skill'],'Python')
        self.assertEqual(self.count(PositionRevision),1);self.assertEqual(self.count(PositionRequirement),1)

    def test_duplicate_names_and_requirements_rejected(self):
        skill=self.skill();p=self.profile(skill)
        self.assertEqual(self.client.post('/api/positions',json={'name':p['name'].upper()}).status_code,409)
        self.assertEqual(self.client.post('/api/positions',json={'name':'Other','requirements':[{'skill_id':skill['id']},{'skill_id':skill['id']}]}).status_code,422)

    def test_inactive_skill_is_not_a_new_requirement(self):
        skill=self.skill();self.db.execute(update(Skill).values(status='INACTIVE'));self.db.commit()
        self.assertEqual(self.client.post('/api/positions',json={'name':'Other','requirements':[{'skill_id':skill['id']}]}).status_code,422)
        self.assertEqual(self.count(PositionProfile),0)

    def test_revision_preserves_old_requirement_text_and_type(self):
        skill=self.skill();p=self.profile(skill);old_id=p['requirements'][0]['id']
        new=self.edit(p,requirements=[{'skill_id':skill['id'],'requirement_type':'RECOMMENDED','rationale':'Yeni sürüm'}])
        self.assertEqual(new['version'],2);self.assertNotEqual(new['requirements'][0]['id'],old_id)
        old=self.client.get(f"/api/positions/{p['id']}?version=1").json();self.assertEqual(old['requirements'][0]['requirement_type'],'REQUIRED');self.assertFalse(old['can_edit'])

    def test_stale_profile_update_is_conflict(self):
        p=self.profile();self.edit(p,name='Changed')
        self.assertEqual(self.client.put(f"/api/positions/{p['id']}",json={'name':'Stale','expected_version':1}).status_code,409)

    def test_inactive_existing_skill_can_be_retained_when_deactivating_profile(self):
        skill=self.skill();p=self.profile(skill);self.db.execute(update(Skill).values(status='INACTIVE'));self.db.commit()
        new=self.edit(p,status='INACTIVE');self.assertEqual(new['requirements'][0]['skill_id'],skill['id'])

    def test_snapshot_and_audit_database_guards(self):
        p=self.profile(self.skill())
        for command in ("UPDATE position_requirements SET rationale='overwrite'",'DELETE FROM position_profiles','DELETE FROM position_revisions',"UPDATE position_revisions SET snapshot_json='{}'",'DELETE FROM position_audit'):
            with self.assertRaises(IntegrityError):self.db.execute(text(command));self.db.commit()
            self.db.rollback()
        rev=self.db.scalar(select(PositionRevision));req=self.db.scalar(select(PositionRequirement))
        with self.assertRaises(IntegrityError):
            self.db.add(PositionRequirement(revision_id=rev.id,skill_id=req.skill_id,skill_name='Injected',requirement_type='REQUIRED',created_by=self.actor.user_id));self.db.commit()
        self.db.rollback()

    def test_assignment_is_optional_and_auth_role_unchanged(self):
        p=self.profile();a=self.assign(p);self.assertEqual(a['version'],1)
        self.db.expire_all();self.assertEqual(self.db.get(PortalUser,self.people['employee'].user_id).role,'EMPLOYEE')
        self.assign(None,expected=1);self.actor=self.people['employee'];self.assertFalse(self.client.get('/api/positions/mine').json()['assigned'])

    def test_inactive_profile_rejects_new_assignment_but_keeps_existing_view(self):
        p=self.profile();self.assign(p);self.edit(p,status='INACTIVE')
        self.assertEqual(self.client.put('/api/positions/users/'+str(self.people['employee2'].user_id),json={'profile_id':p['id'],'expected_version':0}).status_code,422)
        self.actor=self.people['employee'];self.assertEqual(self.client.get('/api/positions/mine').json()['profile']['status'],'INACTIVE')

    def test_assignment_version_conflict(self):
        p=self.profile();self.assign(p)
        self.assertEqual(self.client.put('/api/positions/users/'+str(self.people['employee'].user_id),json={'profile_id':None,'expected_version':0}).status_code,409)

    def test_no_evidence_is_neutral_and_no_global_score(self):
        p=self.profile(self.skill());self.assign(p);self.actor=self.people['employee']
        data=self.client.get('/api/positions/mine').json();r=data['requirements'][0]
        self.assertEqual(r['state'],'NO_EVIDENCE');self.assertEqual(r['evidence_count'],0);self.assertEqual(data['requirement_version'],1)
        self.assertNotIn('score',json.dumps(data));self.assertNotIn('percentage',json.dumps(data));self.assertIsNone(r['last_evidence_at'])

    def test_open_need_is_an_independent_development_signal(self):
        skill=self.skill();p=self.profile(skill);self.assign(p);record,flow=self.case();self.need(record,skill)
        self.actor=self.people['employee'];r=self.client.get('/api/positions/mine').json()['requirements'][0]
        self.assertTrue(r['development_signal']);self.assertEqual(r['open_need_count'],1);self.assertFalse(r['completed_training'])

    def test_position_change_preserves_evidence(self):
        skill=self.skill();p=self.profile(skill);other=self.profile(name='Other');self.assign(p);record,flow=self.case();self.need(record,skill)
        before=self.count(SkillEvidence);self.assign(other,expected=1);self.assertEqual(self.count(SkillEvidence),before)
        self.actor=self.people['employee'];self.assertEqual(self.client.get('/api/positions/mine').json()['requirements'],[])

    def test_scope_blocks_management_and_other_user_gap(self):
        p=self.profile(self.skill());self.assign(p)
        for name in ('employee','employee2','tech','engineering'):
            self.actor=self.people[name]
            for url in ('/api/positions','/api/positions/users','/api/positions/planning',f"/api/positions/{p['id']}/aggregate"):
                self.assertEqual(self.client.get(url).status_code,403,url)
        self.actor=self.people['employee2'];self.assertFalse(self.client.get('/api/positions/mine?user_id='+str(self.people['employee'].user_id)).json()['assigned'])

    def test_small_group_aggregate_suppresses_personal_counts(self):
        skill=self.skill();p=self.profile(skill);self.assign(p);record,flow=self.case();self.need(record,skill)
        data=self.client.get(f"/api/positions/{p['id']}/aggregate").json()
        self.assertTrue(data['suppressed']);self.assertIsNone(data['assigned_user_count']);self.assertIsNone(data['requirements'][0]['users_with_evidence'])
        self.assertNotIn('employee',json.dumps(data))

    def test_large_group_suppresses_small_evidence_and_need_cells(self):
        skill=self.skill();p=self.profile(skill)
        for person in ('employee','employee2','tech','tech2','engineering'):self.assign(p,person)
        for _ in range(5):
            record,flow=self.case();self.need(record,skill)
        data=self.client.get(f"/api/positions/{p['id']}/aggregate").json()
        self.assertEqual(data['assigned_user_count'],5)
        self.assertIsNone(data['requirements'][0]['users_with_evidence']);self.assertIsNone(data['requirements'][0]['open_need_count'])

    def test_planned_demand_is_separate_and_does_not_create_observed_need(self):
        skill=self.skill();p=self.profile(skill)
        r=self.client.get('/api/positions/planning').json()['items'][0]
        self.assertEqual(r['planned_profiles'],1);self.assertEqual(r['active_demand'],0);self.assertFalse(r['planning_signal'])
        self.edit(p,status='INACTIVE');self.assertEqual(self.client.get('/api/positions/planning').json()['items'][0]['planned_profiles'],0)

    def test_request_shortcut_requires_explicit_submission_and_snapshots_version(self):
        skill=self.skill();p=self.profile(skill);self.assign(p);self.actor=self.people['employee']
        self.client.get('/api/positions/mine');self.assertEqual(self.count(RequestRecord),0)
        payload={'text':'Python yetkinliği için kendi gelişim ihtiyacım.','position_requirement_id':p['requirements'][0]['id'],'idempotency_key':'position-request-1'}
        result=self.client.post('/api/requests/analyze',json=payload);self.assertEqual(result.status_code,202,result.text)
        request_id=result.json()['request_id'];self.assertEqual(self.count(AnalysisRun),1)
        self.assertEqual(self.client.post('/api/requests/analyze',json=payload).json()['request_id'],request_id)
        self.edit(p,name='Updated position',requirements=[]);self.actor=self.people['employee']
        old=self.client.get('/api/requests/'+str(request_id)).json()['position_source'];self.assertEqual(old['position_version'],1);self.assertEqual(old['skill'],'Python')
        self.assertEqual(self.count(SkillEvidence),0)

    def test_forged_stale_or_reused_source_cannot_create_request(self):
        p=self.profile(self.skill());req=p['requirements'][0]['id'];self.assign(p)
        self.actor=self.people['employee2'];payload={'text':'Sentetik gelişim ihtiyacı','position_requirement_id':req,'idempotency_key':'source-retry-1'}
        self.assertEqual(self.client.post('/api/requests/analyze',json=payload).status_code,404)
        self.edit(p,name='New version');self.actor=self.people['employee'];self.assertEqual(self.client.post('/api/requests/analyze',json=payload).status_code,409)
        self.assertEqual(self.count(RequestRecord),0)

    def test_retry_cannot_change_original_requirement_source(self):
        p=self.profile(self.skill());self.assign(p);self.actor=self.people['employee']
        payload={'text':'Sentetik yeni gelişim ihtiyacı','idempotency_key':'source-immutable-key','position_requirement_id':p['requirements'][0]['id']}
        result=self.client.post('/api/requests/analyze',json=payload);self.assertEqual(result.status_code,202,result.text)
        payload['position_requirement_id']=None
        self.assertEqual(self.client.post('/api/requests/analyze',json=payload).status_code,409);self.assertEqual(self.count(RequestRecord),1)

class PositionEvidenceTests(PositionFixture,unittest.TestCase):
    edit=skill_fixtures.SkillLifecycleTests.edit
    edit_payload=skill_fixtures.SkillLifecycleTests.edit_payload
    finish=skill_fixtures.SkillLifecycleTests.finish
    create=skill_fixtures.SkillLifecycleTests.create
    action=skill_fixtures.SkillLifecycleTests.action
    source=skill_fixtures.SkillLifecycleTests.source
    ready=skill_fixtures.SkillLifecycleTests.ready
    draft=skill_fixtures.SkillLifecycleTests.draft
    metadata=skill_fixtures.SkillLifecycleTests.metadata
    publish_action=skill_fixtures.SkillLifecycleTests.publish_action
    mapped=skill_fixtures.SkillLifecycleTests.mapped
    live_version=skill_fixtures.SkillLifecycleTests.live_version
    train=skill_fixtures.SkillLifecycleTests.train
    evaluate=skill_fixtures.SkillLifecycleTests.evaluate

    def test_completion_and_authorized_outcome_remain_distinct_evidence(self):
        skill,version,dev,record,flow=self.live_version();p=self.profile(skill);self.assign(p)
        session=self.train(version,record);self.actor=self.people['employee'];row=self.client.get('/api/positions/mine').json()['requirements'][0]
        self.assertEqual(row['state'],'DEVELOPMENT_EVIDENCE');self.assertTrue(row['completed_training']);self.assertFalse(row['authorized_outcome'])
        self.evaluate(session,'APPLICATION','AUTHORIZED_REVIEWER');self.actor=self.people['employee'];row=self.client.get('/api/positions/mine').json()['requirements'][0]
        self.assertEqual(row['state'],'OUTCOME_EVIDENCE');self.assertTrue(row['authorized_outcome']);self.assertTrue(row['development_signal'])

    def test_recommendations_include_only_published_exact_skill_versions(self):
        skill,version,dev,record,flow=self.live_version();p=self.profile(skill);self.assign(p);self.actor=self.people['employee']
        row=self.client.get('/api/positions/mine').json()['requirements'][0];self.assertEqual(row['courses'][0]['id'],version['id'])
        old=self.db.get(CourseVersion,version['id']);old.state='ARCHIVED';old.revision+=1;self.db.commit()
        self.assertEqual(self.client.get('/api/positions/mine').json()['requirements'][0]['courses'],[])
