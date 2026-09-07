import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from sqlalchemy import select, update, text
from sqlalchemy.exc import IntegrityError
import test_operations as fixtures
from app import development as dev, operations as ops
from app.models import (DevelopmentItem, DevelopmentOutcome, DevelopmentModule, DevelopmentTopic, DevelopmentEvent,
    Course, DocumentIndex, RequestReferral, RequestEvent, RequestWorkflow, Notification, OperationOutbox, Delegation)
from app.schemas import DevelopmentCreate
from app.time_policy import utc_now
from app.utils import json_dumps, json_loads


class DevelopmentTests(unittest.TestCase):
    setUp = fixtures.OperationsTests.setUp
    tearDown = fixtures.OperationsTests.tearDown
    case = fixtures.OperationsTests.case
    delegate = fixtures.OperationsTests.delegate
    count = fixtures.OperationsTests.count

    def source(self, enrichment=False, assignee=None):
        record, flow = self.case('REFERRED', 'TECHNICAL_DESIGN', assignee)
        data = json_loads(flow.result_json, {})
        data['classification']['requirements'] = [{'label': 'İşlem sırasını uygulayabilmek'}]
        data['coverage']['missing_topics'] = ['Uygulama örnekleri']
        course_id = None
        if enrichment:
            course = Course(code='SYNTHETIC', name='Sentetik mevcut ders', pdf_path='synthetic.pdf')
            self.db.add(course); self.db.flush(); course_id = course.id
            self.db.add(DocumentIndex(path_key='synthetic.pdf', course_id=course.id, content_hash='a'*64))
            data['courses'] = [{'course_id': course.id, 'course_name': course.name}]
            data['coverage'].update(fit_percent=60, status='KISMEN_VAR')
        flow.result_json = json_dumps(data); self.db.commit()
        self.actor = self.people['tech']
        return record, flow, {'source_request_id': record.id, 'expected_request_version': flow.version,
            'work_type': 'COURSE_ENRICHMENT' if enrichment else 'NEW_COURSE', 'source_course_id': course_id}

    def create(self, enrichment=False, assignee=None):
        record, flow, payload = self.source(enrichment, assignee)
        result = self.client.post('/api/development', json=payload)
        self.assertEqual(result.status_code, 201, result.text)
        return result.json(), record, flow, payload

    def edit_payload(self, data):
        return {'expected_version': data['version'], 'title': 'İnsan tarafından tasarlanan eğitim',
            'summary': 'İnsan tarafından netleştirilen eğitim ihtiyacı.',
            'brief': {'target_output': 'İşlem adımlarını doğru uygulamak', 'missing_topics': ['Uygulama'],
                      'change_notes': 'Uygulama modülü eklenecek', 'excess_notes': 'İleri seviye kapsam dışı'},
            'outcomes': [{'text': 'İşlem adımlarını uygulayabilir'}, {'text': 'Sonucu doğrulayabilir'}],
            'modules': [{'title': 'Uygulama', 'description': 'İş üzerinde uygulama',
                         'topics': [{'title': 'İşlem sırası', 'description': 'Örnek senaryo'}]}]}

    def edit(self, data, payload=None):
        response = self.client.patch(f"/api/development/{data['id']}", json=payload or self.edit_payload(data))
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def action(self, data, code, expected=200, **extra):
        response = self.client.post(f"/api/development/{data['id']}/actions", json={
            'expected_version': data['version'], 'action': code, **extra})
        self.assertEqual(response.status_code, expected, response.text)
        return response.json()

    def review(self):
        data, record, flow, payload = self.create()
        data = self.edit(data)
        for action in ('START_ANALYSIS', 'START_DESIGN', 'SUBMIT_REVIEW'):
            data = self.action(data, action)
        return data, record, flow, payload

    def test_new_course_is_separate_idempotent_and_suggestions_not_approved(self):
        data, record, flow, payload = self.create()
        again = self.client.post('/api/development', json=payload).json()
        self.assertEqual(again['id'], data['id']); self.assertEqual(self.count(DevelopmentItem), 1)
        self.assertEqual(data['outcomes'], []); self.assertEqual(data['content_revision'], 0)
        self.assertEqual(data['source_context']['suggested_outcomes'], ['İşlem sırasını uygulayabilmek'])
        self.db.expire_all(); self.assertEqual(self.db.get(RequestWorkflow, record.id).status, 'REFERRED')

    def test_enrichment_preserves_course_and_fingerprint(self):
        data, _, _, payload = self.create(True)
        self.assertEqual(data['source_course']['id'], payload['source_course_id'])
        self.assertEqual(data['source_course']['source_hash'], 'a'*64)
        self.assertEqual(data['source_context']['fit_percent'], 60)

    def test_unverified_and_wrong_type_or_course_rejected(self):
        record, _, payload = self.source(True)
        response = self.client.post('/api/development', json={**payload, 'source_course_id': None})
        self.assertEqual(response.status_code, 422)
        response = self.client.post('/api/development', json={**payload, 'work_type': 'NEW_COURSE'})
        self.assertEqual(response.status_code, 422)
        self.db.get(RequestReferral, record.id).training_need_confirmed = False; self.db.commit()
        self.assertEqual(self.client.post('/api/development', json=payload).status_code, 404)

    def test_wrong_unit_cannot_read_edit_or_review(self):
        data, _, _, _ = self.create(); self.actor = self.people['engineering']
        self.assertEqual(self.client.get(f"/api/development/{data['id']}").status_code, 404)
        self.assertEqual(self.client.patch(f"/api/development/{data['id']}", json=self.edit_payload(data)).status_code, 404)
        self.assertEqual(self.client.get('/api/development').json()['total'], 0)

    def test_login_required_and_analyst_is_read_only(self):
        data, _, _, _ = self.create(); self.actor = None
        self.assertEqual(self.client.get('/api/development').status_code, 401)
        self.actor = self.people['analyst']; row = self.client.get(f"/api/development/{data['id']}").json()
        self.assertFalse(row['can_edit']); self.assertEqual(row['actions'], [])

    def test_assignee_and_valid_delegate_real_actor_preserved(self):
        data, _, _, _ = self.create(assignee='tech')
        delegation = self.delegate('tech', 'tech2'); self.actor = self.people['tech2']
        url = f"/api/development/{data['id']}"
        self.assertEqual(self.client.patch(url, json=self.edit_payload(data)).status_code, 403)
        result = self.client.patch(url, json=self.edit_payload(data), headers={'X-Delegation-ID': str(delegation['id'])})
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual(result.json()['assignee']['id'], self.people['tech'].user_id)
        event = self.db.scalar(select(DevelopmentEvent).where(DevelopmentEvent.action == 'EDIT'))
        self.assertEqual(event.actor_id, self.people['tech2'].user_id)
        self.assertEqual(json_loads(event.delegation_json,{})['delegator_id'], self.people['tech'].user_id)

    def test_expired_revoked_and_unrelated_delegates_denied(self):
        data, _, _, _ = self.create(assignee='tech'); delegation = self.delegate('tech', 'tech2')
        self.actor = self.people['tech2']; url = f"/api/development/{data['id']}"
        row = self.db.get(Delegation, delegation['id']); row.end_at = utc_now()-timedelta(seconds=1); self.db.commit()
        self.assertEqual(self.client.get(url, headers={'X-Delegation-ID': str(row.id)}).status_code, 403)
        row.end_at=utc_now()+timedelta(hours=1); row.active=False; self.db.commit()
        self.assertEqual(self.client.get(url, headers={'X-Delegation-ID': str(row.id)}).status_code, 403)
        row.active=True;self.db.get(DevelopmentItem,data['id']).assignee_id=None;self.db.commit()
        self.assertEqual(self.client.get(url, headers={'X-Delegation-ID': str(row.id)}).status_code, 403)

    def test_valid_and_invalid_lifecycle_and_required_fields(self):
        data, _, _, _ = self.create(); self.action(data, 'APPROVE', 422)
        data = self.action(data, 'START_ANALYSIS'); self.action(data, 'START_DESIGN', 422)
        data = self.edit(data); data = self.action(data, 'START_DESIGN')
        data = self.action(data, 'SUBMIT_REVIEW'); self.assertEqual(data['state'], 'REVIEW')
        self.assertEqual(self.client.patch(f"/api/development/{data['id']}", json=self.edit_payload(data)).status_code, 403)

    def test_outcome_crud_order_and_timestamps(self):
        data, _, _, _ = self.create(); data = self.edit(data); original = data['outcomes']
        payload = self.edit_payload(data); payload['outcomes'] = [
            {'id': original[1]['id'], 'text': 'Güncellenen kazanım'}, {'id': original[0]['id'], 'text': original[0]['text']}]
        data = self.edit(data, payload)
        self.assertEqual([r['id'] for r in data['outcomes']], [original[1]['id'],original[0]['id']])
        self.assertEqual(data['outcomes'][1]['created_at'], original[0]['created_at'])
        payload = self.edit_payload(data); payload['outcomes'] = [{'id': original[0]['id'], 'text': original[0]['text']}]
        data=self.edit(data,payload);self.assertEqual(len(data['outcomes']),1)

    def test_outline_nested_update_and_cross_item_ids_rollback(self):
        data, _, _, _ = self.create(); data = self.edit(data)
        payload = self.edit_payload(data); payload['modules'][0]['id'] = data['modules'][0]['id']
        payload['modules'][0]['topics'][0]['id'] = data['modules'][0]['topics'][0]['id']
        payload['modules'][0]['topics'][0]['title'] = 'Düzeltilen konu'
        data=self.edit(data,payload);self.assertEqual(data['modules'][0]['topics'][0]['title'],'Düzeltilen konu')
        payload=self.edit_payload(data);payload['outcomes'][0]['id']=999999
        self.assertEqual(self.client.patch(f"/api/development/{data['id']}",json=payload).status_code,422)
        actual=self.client.get(f"/api/development/{data['id']}").json();self.assertEqual(actual['version'],data['version'])

    def test_human_brief_persists_without_regenerating(self):
        data, record, flow, _ = self.create(); data = self.edit(data)
        flow.result_json='{}';self.db.commit()
        actual=self.client.get(f"/api/development/{data['id']}").json()
        self.assertEqual(actual['summary'],data['summary']);self.assertEqual(actual['brief'],data['brief'])

    def test_revision_reason_and_frozen_review_snapshot(self):
        data, _, _, _ = self.review(); self.action(data,'REQUEST_REVISION',422)
        review_event=next(row for row in data['history'] if row['action']=='SUBMIT_REVIEW')
        snapshot=self.client.get(f"/api/development/{data['id']}/history/{review_event['id']}").json()
        data=self.action(data,'REQUEST_REVISION',note='Örnekleri genişletin')
        data=self.edit(data);self.assertGreater(data['content_revision'],snapshot['content_revision'])
        retained=self.client.get(f"/api/development/{data['id']}/history/{review_event['id']}").json()
        self.assertEqual(snapshot,retained)

    def test_ready_preserves_request_and_catalog_allows_future_revision(self):
        data, record, flow, payload = self.review(); version=flow.version
        data=self.action(data,'APPROVE');self.assertEqual(data['state'],'READY')
        self.db.expire_all();self.assertEqual(self.db.get(RequestWorkflow,record.id).status,'REFERRED')
        self.assertEqual(self.db.get(RequestWorkflow,record.id).version,version);self.assertEqual(self.count(Course),0)
        again=self.client.post('/api/development',json=payload);self.assertEqual(again.status_code,201)
        self.assertNotEqual(again.json()['id'],data['id'])

    def test_stale_edit_assignment_and_review_return_conflict(self):
        data, _, _, _ = self.create(); changed=self.edit(data)
        self.assertEqual(self.client.patch(f"/api/development/{data['id']}",json=self.edit_payload(data)).status_code,409)
        self.action(data,'ASSIGN',409,assignee_id=self.people['tech'].user_id)
        changed=self.action(changed,'START_ANALYSIS');changed=self.action(changed,'START_DESIGN');review=self.action(changed,'SUBMIT_REVIEW')
        self.action({**review,'version':review['version']-1},'APPROVE',409)

    def test_assignment_reuses_unit_check_and_target_date(self):
        data, _, _, _ = self.create();self.action(data,'ASSIGN',422,assignee_id=self.people['engineering'].user_id)
        data=self.action(data,'ASSIGN',assignee_id=self.people['tech'].user_id,target_date='2026-12-10')
        self.assertEqual(data['target_date'],'2026-12-10');self.assertTrue(data['created_at'].endswith('Z'))
        self.assertGreaterEqual(data['aging']['current_stage_seconds'],0)

    def test_notifications_existing_outbox_dedup_and_inbox(self):
        data, _, _, _ = self.create();ops.dispatch_events(self.factory)
        self.assertEqual(self.count(Notification),2)
        self.db.execute(update(OperationOutbox).values(processed_at=None));self.db.commit();ops.dispatch_events(self.factory)
        self.assertEqual(self.count(Notification),2)
        notifications=self.client.get('/api/operations/notifications').json()['items']
        self.assertEqual(notifications[0]['development_id'],data['id'])
        inbox=self.client.get('/api/operations/inbox').json()['items']
        self.assertTrue(any(row.get('development_id')==data['id'] for row in inbox))
        before=self.count(RequestEvent);data=self.edit(data);self.assertEqual(self.count(RequestEvent),before)

    def test_review_revision_notifications_and_ready_leaves_inbox(self):
        data, _, _, _ = self.review();data=self.action(data,'REQUEST_REVISION',note='Uygulamayı genişletin')
        data=self.action(data,'SUBMIT_REVIEW');ops.dispatch_events(self.factory)
        types=set(self.db.scalars(select(Notification.type)))
        self.assertIn('DEV_SUBMIT_REVIEW',types);self.assertIn('DEV_REQUEST_REVISION',types)
        data=self.action(data,'APPROVE')
        self.assertFalse(any(row.get('development_id')==data['id'] for row in self.client.get('/api/operations/inbox').json()['items']))

    def test_referral_revocation_removes_visibility_and_notification_link(self):
        data, record, _, _ = self.create();ops.dispatch_events(self.factory)
        self.db.get(RequestReferral,record.id).active=False;self.db.commit()
        self.assertEqual(self.client.get(f"/api/development/{data['id']}").status_code,404)
        notification=self.client.get('/api/operations/notifications').json()['items'][0]
        self.assertIsNone(notification['development_id']);self.assertIsNone(notification['request_id'])

    def test_request_development_links_and_source_course_immutable(self):
        data,record,_,_=self.create(True)
        result=self.client.get(f'/api/admin/requests/{record.id}').json()
        self.assertEqual(result['development']['items'][0]['id'],data['id'])
        payload=self.edit_payload(data);payload['source_course_id']=999
        self.assertEqual(self.client.patch(f"/api/development/{data['id']}",json=payload).status_code,422)

    def test_concurrent_creation_is_backend_idempotent(self):
        record,flow,payload=self.source()
        def create():
            with self.factory() as db:return dev.create(db,self.people['tech'],DevelopmentCreate(**payload))['id']
        with ThreadPoolExecutor(max_workers=2) as pool: ids=list(pool.map(lambda _:create(),range(2)))
        self.assertEqual(ids[0],ids[1]);self.assertEqual(self.count(DevelopmentItem),1)

    def test_database_audit_cannot_be_overwritten(self):
        data,_,_,_=self.create()
        with self.assertRaises(IntegrityError):self.db.execute(text('UPDATE development_events SET note=:note'),{'note':'tamper'})
        self.db.rollback()

    def test_delegate_inbox_is_scoped_to_assigned_work(self):
        data,_,_,_=self.create(assignee='tech');delegation=self.delegate('tech','tech2');self.actor=self.people['tech2']
        rows=self.client.get('/api/operations/inbox').json()['items']
        row=next(row for row in rows if row.get('development_id')==data['id'])
        self.assertEqual(row['delegation']['id'],delegation['id'])

    def test_concurrent_design_edits_allow_only_one_writer(self):
        data,_,_,_=self.create()
        def edit(index):
            payload=self.edit_payload(data);payload['title']=f'Paralel tasarım {index}'
            return self.client.patch(f"/api/development/{data['id']}",json=payload).status_code
        with ThreadPoolExecutor(max_workers=2) as pool: statuses=list(pool.map(edit,range(2)))
        self.assertEqual(sorted(statuses),[200,409])
        self.assertEqual(self.client.get(f"/api/development/{data['id']}").json()['content_revision'],1)

    def test_active_duplicate_unique_index_and_outline_removal(self):
        data,record,_,_=self.create();data=self.edit(data)
        with self.assertRaises(IntegrityError):
            self.db.add(DevelopmentItem(source_request_id=record.id,work_type='NEW_COURSE',title='Yinelenen iş',
                summary='Sentetik yinelenen iş',responsible_unit='TECHNICAL_DESIGN',created_by=self.people['tech'].user_id))
            self.db.flush()
        self.db.rollback()
        payload=self.edit_payload(data);payload['modules']=[];self.edit(data,payload)
        self.assertEqual(self.count(DevelopmentModule),0);self.assertEqual(self.count(DevelopmentTopic),0)

    def test_closed_request_denies_design_mutation(self):
        data,record,_,_=self.create()
        self.db.get(RequestWorkflow,record.id).status='RESOLVED';self.db.commit()
        self.assertEqual(self.client.patch(f"/api/development/{data['id']}",json=self.edit_payload(data)).status_code,403)
        self.assertEqual(self.client.get(f"/api/development/{data['id']}").json()['actions'],[])

    def test_coverage_reuses_selected_course_needs(self):
        record,flow,payload=self.source(True)
        result=json_loads(flow.result_json,{})
        result['courses'][0]['fit']={'percent':61,'requirements':[
            {'label':'Bilinen adımlar','status':'FULL'},{'label':'Uygulama','status':'PARTIAL'}]}
        flow.result_json=json_dumps(result);self.db.commit()
        data=self.client.post('/api/development',json=payload).json()
        self.assertEqual(data['source_context']['covered_needs'],['Bilinen adımlar'])
        self.assertEqual(data['source_context']['partial_needs'],['Uygulama'])
        self.assertEqual(data['source_context']['fit_percent'],61)
