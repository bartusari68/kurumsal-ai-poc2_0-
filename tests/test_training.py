import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from sqlalchemy import select, update, text, func
from sqlalchemy.exc import IntegrityError
import test_operations as fixtures
import test_publishing as publication_fixtures
from app.models import (Course, CourseCatalog, CourseVersion, TrainingSession, Enrollment, TrainingEvent,
    TrainingNotification, RequestWorkflow, RequestEvent, PortalUser, UserOrganization)
from app import operations, training
from app.time_policy import utc_now


class TrainingTests(unittest.TestCase):
    setUp = fixtures.OperationsTests.setUp
    tearDown = fixtures.OperationsTests.tearDown
    case = fixtures.OperationsTests.case
    delegate = fixtures.OperationsTests.delegate
    count = fixtures.OperationsTests.count

    def catalog(self,state='PUBLISHED',unit='TECHNICAL_DESIGN'):
        course=Course(code='TRAIN-'+str(self.count(Course)),name='Sentetik ders',pdf_path='synthetic.pdf')
        self.db.add(course);self.db.flush()
        version=CourseVersion(course_id=course.id,version_number=1,title='Sentetik ders sürümü',state=state,legacy=True)
        self.db.add(version);self.db.flush()
        self.db.add(CourseCatalog(course_id=course.id,current_version_id=version.id if state=='PUBLISHED' else None,responsible_unit=unit));self.db.commit()
        return version

    def make(self,version=None,**changes):
        version=version or self.catalog();self.actor=self.people['tech']
        payload={'course_version_id':version.id,'responsible_unit':'TECHNICAL_DESIGN','delivery_mode':'IN_PERSON',
            'external_trainer':'Sentetik dış eğitmen','start_at':'2026-10-01T09:00:00+03:00',
            'end_at':'2026-10-01T11:00:00+03:00','location':'Sentetik eğitim salonu',**changes}
        response=self.client.post('/api/training',json=payload)
        self.assertEqual(response.status_code,201,response.text)
        return response.json()

    def action(self,row,code,status=200,**changes):
        response=self.client.post(f"/api/training/{row['id']}/actions",json={
            'expected_version':row['version'],'action':code,**changes})
        self.assertEqual(response.status_code,status,response.text)
        return response.json()

    def enroll(self,row,user='employee',status=201,**extra):
        response=self.client.post(f"/api/training/{row['id']}/enrollments",json={
            'expected_version':row['version'],'user_id':self.people[user].user_id,**extra})
        self.assertEqual(response.status_code,status,response.text)
        return response.json()

    def result(self,row,kind,value,status=200):
        response=self.client.post(f"/api/training/{row['id']}/{kind}",json={
            'expected_version':row['version'],'rows':[{'id':e['id'],'version':e['version'],kind:value}
                for e in row['enrollments'] if e['status']=='ENROLLED']})
        self.assertEqual(response.status_code,status,response.text)
        return response.json()

    def edit_payload(self,row,**changes):
        return {'expected_version':row['version'],'title':row['title'],'responsible_unit':row['responsible_unit'],
            'coordinator_id':(row['coordinator'] or {}).get('id'),'trainer_user_id':(row['trainer'] or {}).get('id'),
            'external_trainer':row['external_trainer'],'start_at':row['start_at'],'end_at':row['end_at'],
            'capacity':row['capacity'],'delivery_mode':row['delivery_mode'],'location':row['location'],'online_url':row['online_url'],**changes}

    def test_published_source_and_empty_legacy_unit(self):
        row=self.make(self.catalog(unit=None));self.assertEqual(row['status'],'DRAFT');self.assertIsNone(row['capacity'])
        self.assertEqual(row['course_version_number'],1)

    def test_draft_ready_and_archived_sources_rejected(self):
        self.actor=self.people['tech']
        for state in ('DRAFT','READY_FOR_PUBLISH','ARCHIVED'):
            v=self.catalog(state)
            response=self.client.post('/api/training',json={'course_version_id':v.id,'responsible_unit':'TECHNICAL_DESIGN','delivery_mode':'ONLINE'})
            self.assertEqual(response.status_code,422,response.text)
        self.assertEqual(self.count(TrainingSession),0)

    def test_database_rejects_unpublished_source(self):
        v=self.catalog('DRAFT')
        with self.assertRaises(IntegrityError):
            self.db.add(TrainingSession(course_version_id=v.id,title='Invalid',responsible_unit='TECHNICAL_DESIGN',delivery_mode='ONLINE',created_by=self.actor.user_id));self.db.commit()
        self.db.rollback()

    def test_wrong_course_unit_and_employee_creation_denied(self):
        v=self.catalog(unit='ENGINEERING_DESIGN');self.actor=self.people['tech']
        payload={'course_version_id':v.id,'responsible_unit':'TECHNICAL_DESIGN','delivery_mode':'ONLINE'}
        self.assertEqual(self.client.post('/api/training',json=payload).status_code,403)
        self.actor=self.people['employee'];self.assertEqual(self.client.post('/api/training',json=payload).status_code,403)

    def test_lifecycle_complete_and_invalid_transitions(self):
        row=self.make();self.action(row,'START',422)
        row=self.action(row,'SCHEDULE');self.action(row,'COMPLETE',422)
        row=self.action(row,'START');self.action(row,'COMPLETE',422)
        row=self.action(row,'FINALIZE_ATTENDANCE');row=self.action(row,'COMPLETE')
        self.assertEqual(row['status'],'COMPLETED');self.action(row,'CANCEL',422,reason='İptal')

    def test_draft_optional_fields_but_schedule_requires_trainer(self):
        row=self.make(external_trainer='',start_at=None,end_at=None,location='')
        self.action(row,'SCHEDULE',422)
        response=self.client.patch(f"/api/training/{row['id']}",json=self.edit_payload(row,start_at='2026-10-01T09:00:00+03:00',end_at='2026-10-01T10:00:00+03:00',location='Salon'))
        self.assertEqual(response.status_code,200,response.text);self.action(response.json(),'SCHEDULE',422)

    def test_online_hybrid_and_timezone_validation(self):
        row=self.make(delivery_mode='ONLINE',location='',online_url='https://example.com/meeting')
        self.assertEqual(row['start_at'],'2026-10-01T06:00:00Z');self.action(row,'SCHEDULE')
        v=self.catalog();base={'course_version_id':v.id,'responsible_unit':'TECHNICAL_DESIGN','delivery_mode':'ONLINE'}
        for extra in ({'start_at':'2026-10-01T09:00:00'},{'online_url':'javascript:alert(1)'},{'capacity':0},{'capacity':1.5},{'location':'Wrong mode'}):
            self.assertEqual(self.client.post('/api/training',json={**base,**extra}).status_code,422)
        row=self.make(delivery_mode='HYBRID');self.action(row,'SCHEDULE',422)

    def test_duplicate_and_capacity(self):
        row=self.make(capacity=1);row=self.enroll(row)
        self.enroll(row,status=409);self.enroll(row,'employee2',409)
        self.assertEqual(self.count(Enrollment),1)

    def test_capacity_last_seat_concurrent(self):
        row=self.make(capacity=1)
        def add(name):
            return self.client.post(f"/api/training/{row['id']}/enrollments",json={'expected_version':row['version'],'user_id':self.people[name].user_id}).status_code
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(add,['employee','employee2']))
        self.assertEqual(sorted(results),[201,409]);self.assertEqual(self.count(Enrollment),1)

    def test_capacity_constraint_protects_direct_sql(self):
        row=self.make(capacity=1);self.enroll(row)
        with self.assertRaises(IntegrityError):
            self.db.add(Enrollment(session_id=row['id'],user_id=self.people['employee2'].user_id));self.db.commit()
        self.db.rollback()

    def test_unique_constraint_protects_direct_sql(self):
        row=self.enroll(self.make())
        with self.assertRaises(IntegrityError):
            self.db.add(Enrollment(session_id=row['id'],user_id=self.people['employee'].user_id));self.db.commit()
        self.db.rollback()

    def test_capacity_cannot_shrink_below_roster(self):
        row=self.enroll(self.enroll(self.make(),'employee'),'employee2')
        response=self.client.patch(f"/api/training/{row['id']}",json=self.edit_payload(row,capacity=1))
        self.assertEqual(response.status_code,409)
        self.db.expire_all();self.assertIsNone(self.db.get(TrainingSession,row['id']).capacity)

    def test_enrollment_removal_releases_seat_and_preserves_row(self):
        row=self.enroll(self.make(capacity=1));e=row['enrollments'][0]
        result=self.client.post(f"/api/training/{row['id']}/enrollments/{e['id']}/remove",json={'expected_version':row['version'],'enrollment_version':e['version']})
        self.assertEqual(result.status_code,200);row=self.enroll(result.json(),'employee2')
        self.assertEqual(row['participant_count'],1);self.assertEqual(len(row['enrollments']),2)

    def test_attendance_authorization_and_phase(self):
        row=self.enroll(self.make());self.result(row,'attendance','ATTENDED',422)
        row=self.action(self.action(row,'SCHEDULE'),'START')
        self.actor=self.people['employee'];self.result(row,'attendance','ATTENDED',403)
        self.actor=self.people['engineering'];self.result(row,'attendance','ATTENDED',404)
        self.actor=self.people['tech'];row=self.result(row,'attendance','ATTENDED');self.assertEqual(row['enrollments'][0]['attendance'],'ATTENDED')

    def test_completion_independent_and_request_not_resolved(self):
        record,flow=self.case('REFERRED','TECHNICAL_DESIGN');before=flow.status
        row=self.enroll(self.make(),source_request_id=record.id);row=self.action(self.action(row,'SCHEDULE'),'START')
        row=self.result(row,'completion','COMPLETED')
        self.assertEqual(row['enrollments'][0]['attendance'],'UNKNOWN');self.assertIsNotNone(row['enrollments'][0]['completed_at'])
        self.db.expire_all();self.assertEqual(self.db.get(RequestWorkflow,record.id).status,before)
        links=training.request_links(self.db,record,flow,'TECHNICAL_DESIGN');self.assertTrue(links[0]['training_completed'])

    def test_source_request_must_belong_to_participant(self):
        record,_=self.case('REFERRED','TECHNICAL_DESIGN');row=self.make()
        self.enroll(row,'employee2',422,source_request_id=record.id)

    def test_bulk_results_are_atomic_on_stale_enrollment(self):
        row=self.enroll(self.enroll(self.make(),'employee'),'employee2');row=self.action(self.action(row,'SCHEDULE'),'START')
        entries=row['enrollments'];payload={'expected_version':row['version'],'rows':[
            {'id':entries[0]['id'],'version':entries[0]['version'],'attendance':'ATTENDED'},
            {'id':entries[1]['id'],'version':999,'attendance':'ABSENT'}]}
        response=self.client.post(f"/api/training/{row['id']}/attendance",json=payload);self.assertEqual(response.status_code,409)
        self.db.expire_all();self.assertEqual(set(self.db.scalars(select(Enrollment.attendance))),{'UNKNOWN'})

    def test_parallel_attendance_and_completion_cannot_overwrite(self):
        row=self.enroll(self.make());row=self.action(self.action(row,'SCHEDULE'),'START');entry=row['enrollments'][0]
        def save(kind):
            value='ATTENDED' if kind=='attendance' else 'COMPLETED'
            return self.client.post(f"/api/training/{row['id']}/{kind}",json={'expected_version':row['version'],'rows':[{'id':entry['id'],'version':entry['version'],kind:value}]}).status_code
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(save,['attendance','completion']))
        self.assertEqual(sorted(results),[200,409])

    def test_completion_requires_explicit_results_and_attendance_finalization(self):
        row=self.enroll(self.make());row=self.action(self.action(row,'SCHEDULE'),'START')
        self.action(row,'FINALIZE_ATTENDANCE',422)
        row=self.result(row,'attendance','ABSENT');row=self.action(row,'FINALIZE_ATTENDANCE');self.action(row,'COMPLETE',422)
        row=self.result(row,'completion','NOT_COMPLETED');row=self.action(row,'COMPLETE');self.assertEqual(row['status'],'COMPLETED')
        row=self.result(row,'attendance','EXCUSED');self.assertIsNone(row['attendance_finalized_at'])

    def test_cancel_reason_notifications_and_terminal_guards(self):
        row=self.enroll(self.make());self.action(row,'CANCEL',422)
        row=self.action(row,'CANCEL',reason='Sentetik iptal gerekçesi')
        for code in ('START','SCHEDULE','COMPLETE','FINALIZE_ATTENDANCE'):self.action(row,code,422)
        self.result(row,'attendance','ATTENDED',422);self.result(row,'completion','COMPLETED',422)
        self.actor=self.people['employee'];notes=self.client.get('/api/operations/notifications').json()['items']
        self.assertTrue(any(n.get('session_id')==row['id'] and 'iptal' in n['title'].lower() for n in notes))

    def test_version_immutable_and_new_publication_does_not_retarget_session(self):
        v=self.catalog();row=self.make(v);row=self.action(row,'SCHEDULE')
        self.db.execute(update(CourseVersion).where(CourseVersion.id==v.id).values(state='ARCHIVED',revision=CourseVersion.revision+1))
        newer=CourseVersion(course_id=v.course_id,version_number=2,title='Yeni sürüm',state='PUBLISHED')
        self.db.add(newer);self.db.flush();self.db.get(CourseCatalog,v.course_id).current_version_id=newer.id;self.db.commit()
        self.assertEqual(self.client.get(f"/api/training/{row['id']}").json()['course_version_id'],v.id)
        with self.assertRaises(IntegrityError):self.db.execute(update(TrainingSession).where(TrainingSession.id==row['id']).values(course_version_id=newer.id));self.db.commit()
        self.db.rollback()
        response=self.client.patch(f"/api/training/{row['id']}",json=self.edit_payload(row,course_version_id=newer.id));self.assertEqual(response.status_code,422)

    def test_delegation_actor_and_revocation(self):
        row=self.make(coordinator_id=self.people['tech'].user_id);grant=self.delegate('tech','tech2');self.actor=self.people['tech2']
        self.assertEqual(self.client.post(f"/api/training/{row['id']}/actions",json={'expected_version':row['version'],'action':'SCHEDULE'}).status_code,403)
        response=self.client.post(f"/api/training/{row['id']}/actions",headers={'X-Delegation-ID':str(grant['id'])},json={'expected_version':row['version'],'action':'SCHEDULE'})
        self.assertEqual(response.status_code,200,response.text);row=response.json();event=row['history'][-1]
        self.assertEqual(event['actor'],'tech2');self.assertEqual(event['details']['delegation']['delegator_id'],self.people['tech'].user_id)
        operations.revoke_delegation(self.db,self.people['tech'],grant['id'])
        self.assertEqual(self.client.get(f"/api/training/{row['id']}",headers={'X-Delegation-ID':str(grant['id'])}).status_code,403)

    def test_delegation_inbox_and_org_boundary(self):
        row=self.make(coordinator_id=self.people['tech'].user_id);grant=self.delegate('tech','tech2')
        items=operations.inbox(self.db,self.people['tech2'])['items'];training_items=[i for i in items if i.get('kind')=='training']
        self.assertEqual(training_items[0]['delegation']['id'],grant['id'])
        self.db.add(UserOrganization(user_id=self.people['tech2'].user_id,unit='Different'));self.db.commit()
        self.assertFalse(training.inbox_items(self.db,self.people['tech2']))

    def test_employee_roster_privacy_and_unrelated_visibility(self):
        row=self.enroll(self.enroll(self.make(),'employee'),'employee2');self.actor=self.people['employee']
        data=self.client.get(f"/api/training/{row['id']}").json();self.assertEqual(len(data['enrollments']),1);self.assertFalse(data['actions'])
        self.assertEqual(self.client.get('/api/training/options?session_id='+str(row['id'])).status_code,403)
        self.actor=self.people['engineering'];self.assertEqual(self.client.get(f"/api/training/{row['id']}").status_code,404)
        self.assertEqual(self.client.get('/api/training').json()['total'],0)

    def test_notification_count_read_ownership_and_no_duplicate_noop(self):
        row=self.enroll(self.make());self.actor=self.people['employee'];notes=self.client.get('/api/operations/notifications').json()
        note=notes['items'][0];self.assertLess(note['id'],0);self.assertEqual(self.client.get('/api/operations/notifications/count').json()['unread_count'],1)
        self.actor=self.people['employee2'];self.assertEqual(self.client.post(f"/api/operations/notifications/{note['id']}/read").status_code,404)
        self.actor=self.people['employee'];self.client.post('/api/operations/notifications/read-all');self.assertEqual(self.client.get('/api/operations/notifications/count').json()['unread_count'],0)
        self.actor=self.people['tech'];before=self.count(TrainingNotification)
        self.client.patch(f"/api/training/{row['id']}",json=self.edit_payload(row));self.assertEqual(self.count(TrainingNotification),before)

    def test_scheduled_meaningful_edit_notifies_and_stale_edit_rejected(self):
        row=self.action(self.enroll(self.make()),'SCHEDULE');before=self.count(TrainingNotification)
        response=self.client.patch(f"/api/training/{row['id']}",json=self.edit_payload(row,start_at='2026-10-01T12:00:00Z',end_at='2026-10-01T13:00:00Z'))
        self.assertEqual(response.status_code,200,response.text);self.assertGreater(self.count(TrainingNotification),before)
        self.assertEqual(self.client.patch(f"/api/training/{row['id']}",json=self.edit_payload(row)).status_code,409)

    def test_audit_sql_protected(self):
        self.make()
        with self.assertRaises(IntegrityError):self.db.execute(text("UPDATE training_events SET actor_name='fake'"));self.db.commit()
        self.db.rollback()

    def test_queue_date_search_and_pagination(self):
        self.make(start_at='2026-10-01T00:30:00+03:00',end_at='2026-10-01T01:30:00+03:00')
        self.make(start_at='2026-10-02T00:30:00+03:00',end_at='2026-10-02T01:30:00+03:00')
        self.assertEqual(self.client.get('/api/training?day=2026-10-01').json()['total'],1)
        self.assertEqual(len(self.client.get('/api/training?limit=1&offset=1').json()['items']),1)
        self.assertEqual(self.client.get('/api/training?search=does-not-exist').json()['total'],0)

    def test_existing_request_queue_preserved_and_union_pagination(self):
        self.case(assignee='analyst');self.case(assignee='analyst2');self.case();self.case('RESOLVED')
        before=operations.inbox(self.db,self.people['analyst'])
        row=self.make();after=operations.inbox(self.db,self.people['analyst'])
        self.assertEqual([r['request_id'] for r in before['items']],[r['request_id'] for r in after['items']])
        self.assertEqual(before['total'],after['total'])
        full=operations.inbox(self.db,self.people['tech']);pages=[operations.inbox(self.db,self.people['tech'],i,1)['items'][0] for i in range(full['total'])]
        self.assertEqual([(r.get('kind'),r['request_id']) for r in full['items']],[(r.get('kind'),r['request_id']) for r in pages])

    def test_direct_duplicate_event_notification_is_deduplicated(self):
        from sqlalchemy.dialects.sqlite import insert
        row=self.enroll(self.make());note=self.db.scalar(select(TrainingNotification))
        self.db.execute(insert(TrainingNotification).values(recipient_id=note.recipient_id,session_id=note.session_id,
            source_event_id=note.source_event_id,title=note.title,message=note.message)
            .on_conflict_do_nothing(index_elements=['source_event_id','recipient_id']))
        self.db.commit();self.assertEqual(self.count(TrainingNotification),1)

    def test_database_migration_is_idempotent_and_preserves_existing_rows(self):
        from app.database import Base
        from app.training_models import install_guards
        record,flow=self.case('REFERRED','TECHNICAL_DESIGN');self.catalog()
        before={table.name:self.db.execute(select(table)).all() for table in Base.metadata.tables.values()}
        for _ in range(2):Base.metadata.create_all(self.engine);install_guards(self.engine)
        after={table.name:self.db.execute(select(table)).all() for table in Base.metadata.tables.values()}
        self.assertEqual(before,after)

    def test_internal_trainer_does_not_gain_operational_privileges(self):
        row=self.make(external_trainer='',trainer_user_id=self.people['employee'].user_id)
        self.assertEqual(self.count(PortalUser),7)
        self.actor=self.people['employee'];data=self.client.get(f"/api/training/{row['id']}").json()
        self.assertFalse(data['actions']);self.assertFalse(any(data['capabilities'].values()))


class TrainingTraceTests(unittest.TestCase):
    setUp=publication_fixtures.PublishingTests.setUp
    tearDown=publication_fixtures.PublishingTests.tearDown
    case=publication_fixtures.PublishingTests.case
    count=publication_fixtures.PublishingTests.count
    create=publication_fixtures.PublishingTests.create
    edit_payload=publication_fixtures.PublishingTests.edit_payload
    edit=publication_fixtures.PublishingTests.edit
    action=publication_fixtures.PublishingTests.action
    ready=publication_fixtures.PublishingTests.ready
    finish=publication_fixtures.PublishingTests.finish
    draft=publication_fixtures.PublishingTests.draft
    metadata=publication_fixtures.PublishingTests.metadata
    publish_action=publication_fixtures.PublishingTests.publish_action
    published=publication_fixtures.PublishingTests.published

    def source(self,enrichment=False,assignee=None):
        from app.models import RequestDecision
        record,flow,payload=publication_fixtures.PublishingTests.source(self,enrichment,assignee)
        decision=RequestDecision(request_id=record.id,reviewer_id=self.people['analyst'].user_id,
            reviewer_name='analyst',reviewer_role='NEEDS_ANALYST',request_version=flow.version,
            outcome='APPROVED',reason='Doğrulanmış sentetik eğitim ihtiyacı',original_ai_json=flow.result_json,
            training_need_confirmed=True,actual_department='TECHNICAL_DESIGN')
        self.db.add(decision);self.db.commit();self.decision_id=decision.id
        return record,flow,payload

    def test_end_to_end_request_decision_development_version_session_completion(self):
        version,development,record,flow,payload=self.published()
        response=self.client.post('/api/training',json={'course_version_id':version['id'],
            'responsible_unit':'TECHNICAL_DESIGN','delivery_mode':'ONLINE','online_url':'https://example.com/training',
            'external_trainer':'Sentetik eğitmen','start_at':'2026-10-01T09:00:00+03:00','end_at':'2026-10-01T11:00:00+03:00'})
        self.assertEqual(response.status_code,201,response.text);row=response.json()
        self.assertEqual(row['trace']['development_id'],development['id']);self.assertEqual(row['trace']['request_id'],record.id)
        self.assertEqual(row['trace']['decision_id'],self.decision_id)
        response=self.client.post(f"/api/training/{row['id']}/enrollments",json={'expected_version':row['version'],
            'user_id':self.people['employee'].user_id,'source_request_id':record.id});self.assertEqual(response.status_code,201);row=response.json()
        for action in ('SCHEDULE','START'):
            row=self.client.post(f"/api/training/{row['id']}/actions",json={'expected_version':row['version'],'action':action}).json()
        e=row['enrollments'][0]
        response=self.client.post(f"/api/training/{row['id']}/completion",json={'expected_version':row['version'],
            'rows':[{'id':e['id'],'version':e['version'],'completion':'COMPLETED'}]});self.assertEqual(response.status_code,200)
        self.db.expire_all();self.assertEqual(self.db.get(RequestWorkflow,record.id).status,'REFERRED')
        self.assertTrue(training.request_links(self.db,record,flow,'TECHNICAL_DESIGN')[0]['training_completed'])


if __name__=='__main__':unittest.main()
