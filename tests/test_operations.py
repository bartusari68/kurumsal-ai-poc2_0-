import json
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select, text, update
from sqlalchemy.orm import sessionmaker

from app import operations as ops, workflow_policy as policy
from app.database import Base, get_db
from app.main import app
from app.models import (Delegation, DelegationAudit, Notification, OperationOutbox, EscalationRecord,
    PortalUser, RequestAssignment, RequestDecision, RequestEvent, RequestEventAction, RequestRecord,
    RequestReferral, RequestWorkflow, UserOrganization)
from app.portal_auth import Principal, current_account
from app.schemas import DelegationRequest, WorkflowActionRequest, DecisionRequest
from app.time_policy import utc_now, as_utc, utc_stamp
from app.workflow import record_analysis, request_detail
from app.workflow_core import execute_action, aging


class OperationsTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.engine = create_engine('sqlite:///' + str(Path(self.folder.name) / 'ops.db'), connect_args={'check_same_thread': False})
        Base.metadata.create_all(self.engine)
        self.factory = sessionmaker(bind=self.engine, expire_on_commit=False, autoflush=False)
        self.db = self.factory()
        self.people = {}
        for name, role in [('employee','EMPLOYEE'),('employee2','EMPLOYEE'),('analyst','NEEDS_ANALYST'),
                           ('analyst2','NEEDS_ANALYST'),('tech','TECHNICAL_DESIGN'),('tech2','TECHNICAL_DESIGN'),('engineering','ENGINEERING_DESIGN')]:
            user=PortalUser(username=name,display_name=name,role=role,password_salt='0'*32,password_hash='0'*64)
            self.db.add(user);self.db.flush();self.people[name]=Principal(user.id,name,name,role)
        self.db.commit();self.actor=self.people['analyst']
        def database():
            with self.factory() as db: yield db
        app.dependency_overrides[get_db]=database
        app.dependency_overrides[current_account]=lambda:self.actor
        self.client=TestClient(app)

    def tearDown(self):
        self.client.close();app.dependency_overrides.clear();self.db.close();self.engine.dispose();self.folder.cleanup()

    def count(self, model):
        self.db.expire_all()
        return self.db.scalar(select(func.count()).select_from(model))

    def case(self, state='IN_REVIEW', department=None, assignee=None):
        record=RequestRecord(text='Sentetik operasyon ihtiyacı',topic='Operasyon testi',canonical_intent='test')
        self.db.add(record);self.db.flush()
        record_analysis(self.db,record,{'request_id':record.id,'classification':{'subcategory_id':'OTHER.REVIEW','risk_level':'NORMAL','topic':'Operasyon testi'},
            'coverage':{'status':'YOK','fit_percent':0},'courses':[]},self.people['employee'].token_hash)
        self.db.flush();flow=self.db.get(RequestWorkflow,record.id);flow.status=state
        if state!='IN_REVIEW':self.db.add(RequestEvent(request_id=record.id,status=state,actor='SYSTEM',note='Sentetik başlangıç aşaması'))
        if department:self.db.add(RequestReferral(request_id=record.id,department=department,analysis_summary='Sentetik yönlendirme',training_need_confirmed=True,active=True,analyst_id=self.people['analyst'].user_id))
        if assignee:self.db.add(RequestAssignment(request_id=record.id,responsible_scope=self.people[assignee].role,assignee_id=self.people[assignee].user_id,assigned_by=self.people['analyst'].user_id))
        self.db.commit();return record,flow

    def delegate(self, owner='analyst', delegate='analyst2', start=None, end=None):
        return ops.create_delegation(self.db,self.people[owner],DelegationRequest(delegate_id=self.people[delegate].user_id,
            start_at=start or utc_now()-timedelta(minutes=1),end_at=end or utc_now()+timedelta(hours=1),reason='Sentetik izin'))

    def act(self, record, flow, code='REQUEST_INFO', user='analyst', **extra):
        return execute_action(self.db,record,flow,self.people[user],WorkflowActionRequest(action=code,expected_version=flow.version,note='Sentetik açıklama bilgisi',**extra))

    def test_event_notification_recipient_and_db_deduplication(self):
        record,flow=self.case();self.act(record,flow);ops.dispatch_events(self.factory)
        self.assertEqual(self.count(Notification),1)
        row=self.db.scalar(select(Notification));self.assertEqual(row.recipient_id,self.people['employee'].user_id)
        self.assertEqual(row.type,'REQUEST_INFO')
        self.db.execute(update(OperationOutbox).values(processed_at=None));self.db.commit();ops.dispatch_events(self.factory)
        self.assertEqual(self.count(Notification),1)

    def test_assignment_notification_targets_actual_assignee(self):
        record,flow=self.case();self.act(record,flow,'ASSIGN',assignee_id=self.people['analyst2'].user_id)
        ops.dispatch_events(self.factory);row=self.db.scalar(select(Notification))
        self.assertEqual(row.recipient_id,self.people['analyst2'].user_id)

    def test_notification_failure_does_not_rollback_workflow_and_retries(self):
        record,flow=self.case();self.act(record,flow)
        with patch('app.operations.translate_event',side_effect=RuntimeError('synthetic delivery failure')):ops.dispatch_events(self.factory)
        self.assertEqual(self.db.get(RequestWorkflow,record.id).status,'NEEDS_INFO');self.assertEqual(self.count(Notification),0)
        self.db.execute(update(OperationOutbox).values(retry_at=None));self.db.commit();ops.dispatch_events(self.factory)
        self.assertEqual(self.count(Notification),1)

    def test_notification_read_authorization_and_read_all_do_not_add_audit(self):
        record,flow=self.case();self.act(record,flow);ops.dispatch_events(self.factory)
        row=self.db.scalar(select(Notification));before=self.count(RequestEvent)
        self.assertEqual(self.client.get('/api/operations/notifications').json()['total'],0)
        self.assertEqual(self.client.post(f'/api/operations/notifications/{row.id}/read').status_code,404)
        self.actor=self.people['employee'];self.assertEqual(self.client.get('/api/operations/notifications/count').json()['unread_count'],1)
        self.assertEqual(self.client.post(f'/api/operations/notifications/{row.id}/read').status_code,200)
        self.assertEqual(self.client.get('/api/operations/notifications/count').json()['unread_count'],0)
        self.client.post('/api/operations/notifications/read-all');self.assertEqual(self.count(RequestEvent),before)

    def test_unit_referral_notifies_only_referred_department(self):
        record,flow=self.case('REFERRED','TECHNICAL_DESIGN')
        from app.process import add_process_event
        add_process_event(self.db,request_id=record.id,status='REFERRED',actor='NEEDS_ANALYST',principal=self.people['analyst'],note='Sentetik yönlendirme',action='REFER')
        self.db.commit();ops.dispatch_events(self.factory)
        self.assertEqual(set(self.db.scalars(select(Notification.recipient_id))),{self.people['tech'].user_id,self.people['tech2'].user_id})

    def test_notification_content_is_hidden_after_referral_revocation(self):
        record,flow=self.case('REFERRED','TECHNICAL_DESIGN')
        from app.process import add_process_event
        add_process_event(self.db,request_id=record.id,status='REFERRED',actor='SYSTEM',note='Yönlendirme',action='REFER');self.db.commit();ops.dispatch_events(self.factory)
        self.db.get(RequestReferral,record.id).active=False;self.db.commit();self.actor=self.people['tech']
        result=self.client.get('/api/operations/notifications').json()['items'][0]
        self.assertIsNone(result['request_id']);self.assertIn('erişiminiz',result['title'])

    def test_inbox_only_real_personal_or_unit_actions(self):
        mine,_=self.case(assignee='analyst');other,_=self.case(assignee='analyst2');unit,_=self.case();self.case('RESOLVED')
        rows=ops.inbox(self.db,self.people['analyst'])['items'];self.assertEqual({r['request_id'] for r in rows},{mine.id,unit.id})
        for row in rows:
            self.assertTrue(row['required_actions']);self.assertNotIn(row['required_actions'][0]['code'],('ASSIGN','REOPEN'))

    def test_employee_inbox_does_not_show_waiting_review_as_work(self):
        self.case();info,_=self.case('NEEDS_INFO');self.case('RESOLVED')
        rows=ops.inbox(self.db,self.people['employee'])['items'];self.assertEqual([r['request_id'] for r in rows],[info.id])
        self.assertEqual(rows[0]['required_actions'][0]['code'],'PROVIDE_INFO')

    def test_valid_delegation_preserves_assignment_and_records_actual_decision_actor(self):
        record,flow=self.case(assignee='analyst');delegation=self.delegate();self.actor=self.people['analyst2']
        response=self.client.post(f'/api/admin/requests/{record.id}/decisions',headers={'X-Delegation-ID':str(delegation['id'])},
            json={'outcome':'REJECTED','expected_version':flow.version,'reason':'Sentetik değerlendirmede öneri uygun bulunmadı.'})
        self.assertEqual(response.status_code,200,response.text);self.db.expire_all()
        decision=self.db.scalar(select(RequestDecision));audit=json.loads(decision.original_ai_json)['audit']['delegation']
        self.assertEqual(decision.reviewer_id,self.actor.user_id);self.assertEqual(audit['delegator_id'],self.people['analyst'].user_id)
        self.assertEqual(self.db.get(RequestAssignment,record.id).assignee_id,self.people['analyst'].user_id)

    def test_future_expired_revoked_delegations_cannot_be_used(self):
        record,flow=self.case(assignee='analyst');delegation=self.delegate(start=utc_now()+timedelta(hours=1),end=utc_now()+timedelta(hours=2));self.actor=self.people['analyst2']
        url=f'/api/admin/requests/{record.id}';headers={'X-Delegation-ID':str(delegation['id'])}
        self.assertEqual(self.client.get(url,headers=headers).status_code,403)
        row=self.db.get(Delegation,delegation['id']);row.start_at=utc_now()-timedelta(hours=2);row.end_at=utc_now()-timedelta(hours=1);self.db.commit()
        self.assertEqual(self.client.get(url,headers=headers).status_code,403)
        row.end_at=utc_now()+timedelta(hours=1);row.active=False;self.db.commit()
        self.assertEqual(self.client.get(url,headers=headers).status_code,403)

    def test_wrong_role_and_known_unit_mismatch_rejected(self):
        with self.assertRaises(HTTPException):self.delegate(delegate='tech')
        self.db.add(UserOrganization(user_id=self.people['analyst'].user_id,unit='A'));self.db.add(UserOrganization(user_id=self.people['analyst2'].user_id,unit='B'));self.db.commit()
        with self.assertRaises(HTTPException):self.delegate()
        self.assertEqual(ops.delegation_options(self.db,self.people['analyst']),[])

    def test_delegation_never_opens_unassigned_or_other_units_cases(self):
        assigned,_=self.case('REFERRED','TECHNICAL_DESIGN','tech');other,_=self.case('REFERRED','ENGINEERING_DESIGN','engineering');unassigned,_=self.case('REFERRED','TECHNICAL_DESIGN')
        row=self.delegate('tech','tech2');self.actor=self.people['tech2'];header={'X-Delegation-ID':str(row['id'])}
        self.assertEqual(self.client.get(f'/api/admin/requests/{assigned.id}',headers=header).status_code,200)
        for record in (other,unassigned):self.assertEqual(self.client.get(f'/api/admin/requests/{record.id}',headers=header).status_code,403)
        self.assertEqual(self.client.get('/api/admin/requests',headers=header).status_code,403)

    def test_employee_delegation_scope_is_actionable_owner_requests_only(self):
        record,flow=self.case('NEEDS_INFO');waiting,_=self.case();row=self.delegate('employee','employee2');self.actor=self.people['employee2'];headers={'X-Delegation-ID':str(row['id'])}
        self.assertEqual(self.client.get(f'/api/requests/{record.id}').status_code,404)
        self.assertEqual(self.client.get(f'/api/requests/{waiting.id}',headers=headers).status_code,403)
        result=self.client.post(f'/api/requests/{record.id}/actions',headers=headers,json={'action':'PROVIDE_INFO','expected_version':flow.version,'note':'Sentetik ek bilgiler vekâleten iletildi.'})
        self.assertEqual(result.status_code,200,result.text);self.db.expire_all()
        event=self.db.scalar(select(RequestEventAction).where(RequestEventAction.action=='PROVIDE_INFO'))
        self.assertEqual(json.loads(event.details_json)['delegation']['acting_user_id'],self.actor.user_id)
        self.assertEqual(self.db.get(RequestWorkflow,record.id).owner_hash,self.people['employee'].token_hash)

    def test_delegated_inbox_and_notification_link_use_explicit_context(self):
        record,flow=self.case(assignee='analyst');row=self.delegate();inbox=ops.inbox(self.db,self.people['analyst2'])
        self.assertEqual(inbox['items'][0]['delegation']['id'],row['id'])
        self.act(record,flow,'ASSIGN',assignee_id=self.people['analyst'].user_id);ops.dispatch_events(self.factory)
        value=ops.notifications(self.db,self.people['analyst2'],0,20)['items'][0];self.assertEqual(value['delegation_id'],row['id'])

    def test_permanent_reassignment_is_not_delegation(self):
        record,flow=self.case(assignee='analyst');self.act(record,flow,'ASSIGN',assignee_id=self.people['analyst2'].user_id)
        row=ops.inbox(self.db,self.people['analyst2'])['items'][0];self.assertIsNone(row['delegation'])
        action=self.db.scalar(select(RequestEventAction).where(RequestEventAction.action=='ASSIGN'));self.assertNotIn('delegation',json.loads(action.details_json))

    def test_delegation_revoke_is_owner_only_and_idempotent(self):
        row=self.delegate();self.actor=self.people['analyst2'];url=f"/api/operations/delegations/{row['id']}/revoke"
        self.assertEqual(self.client.post(url).status_code,404);self.actor=self.people['analyst']
        self.assertEqual(self.client.post(url).status_code,200);self.assertEqual(self.client.post(url).status_code,200)
        self.assertEqual(self.db.scalar(select(func.count()).select_from(DelegationAudit).where(DelegationAudit.action=='REVOKED')),1)

    def test_overlap_is_rejected_without_changing_existing_window(self):
        self.delegate()
        with self.assertRaises(HTTPException) as caught:self.delegate()
        self.assertEqual(caught.exception.status_code,409);self.assertEqual(self.count(Delegation),1)

    def test_lifecycle_is_separate_from_request_history_and_deduplicated(self):
        row=self.delegate();ops.delegation_lifecycle(self.db);ops.delegation_lifecycle(self.db)
        self.assertEqual(self.count(DelegationAudit),2);self.assertEqual(self.count(RequestEvent),0)
        d=self.db.get(Delegation,row['id']);d.start_at=utc_now()-timedelta(hours=2);d.end_at=utc_now()-timedelta(hours=1);self.db.commit();ops.delegation_lifecycle(self.db)
        self.assertEqual(self.count(DelegationAudit),3)

    def test_sla_unconfigured_has_no_overdue_or_escalation(self):
        record,flow=self.case();ctx=policy.context(self.db,record,flow)
        self.assertIsNone(aging(self.db,record,flow,ctx)['sla']);ops.check_escalations(self.db)
        self.assertEqual(self.count(EscalationRecord),0)

    def test_sla_aware_aging_and_explicit_approaching_threshold(self):
        record,flow=self.case();record.created_at=utc_now()-timedelta(seconds=80);self.db.commit();ctx=policy.context(self.db,record,flow)
        with patch.dict(policy.SLA_TARGETS,{('IN_REVIEW','REVIEW_REQUEST','NEEDS_ANALYST'):{'target_seconds':100,'approaching_seconds':30}}):
            self.assertEqual(aging(self.db,record,flow,ctx)['sla']['state'],'approaching')

    def test_overdue_without_recipient_does_not_notify_or_log_escalation(self):
        record,flow=self.case();record.created_at=utc_now()-timedelta(hours=1);self.db.commit()
        with patch.dict(policy.SLA_TARGETS,{('IN_REVIEW',None):{'target_seconds':1}}):ops.check_escalations(self.db)
        self.assertEqual(self.count(EscalationRecord),0);self.assertEqual(self.count(Notification),0)

    def test_explicit_escalation_once_and_only_to_authorized_target(self):
        record,flow=self.case();record.created_at=utc_now()-timedelta(hours=1);self.db.commit()
        with patch.dict(policy.SLA_TARGETS,{('IN_REVIEW',None):{'target_seconds':1,'recipient_user_ids':[self.people['analyst2'].user_id,self.people['tech'].user_id]}}):
            ops.check_escalations(self.db);ops.check_escalations(self.db)
        ops.dispatch_events(self.factory);self.assertEqual(self.count(EscalationRecord),1)
        self.assertEqual(list(self.db.scalars(select(Notification.recipient_id))),[self.people['analyst2'].user_id])
        self.assertEqual(self.db.get(RequestWorkflow,record.id).version,1)

    def test_naive_legacy_storage_loads_aware_without_rewriting_bytes(self):
        record,flow=self.case()
        with self.engine.begin() as c:c.execute(text('UPDATE requests SET created_at=:at WHERE id=:id'),{'at':'2026-01-02 03:04:05.000000','id':record.id})
        self.db.expire_all();value=self.db.get(RequestRecord,record.id).created_at
        self.assertEqual(value.tzinfo,timezone.utc);self.assertEqual(utc_stamp(value),'2026-01-02T03:04:05Z')
        self.assertEqual(as_utc(datetime(2026,1,2,3,4,5)),value)

    def test_timezone_offset_is_normalized_on_write(self):
        row=self.delegate(start=datetime(2026,1,1,tzinfo=timezone(timedelta(hours=3))),end=utc_now()+timedelta(hours=1));self.db.expire_all()
        value=self.db.get(Delegation,row['id']).start_at;self.assertEqual(value,datetime(2025,12,31,21,tzinfo=timezone.utc))

    def test_delegation_api_rejects_ambiguous_naive_dates(self):
        reply=self.client.post('/api/operations/delegations',json={'delegate_id':self.people['analyst2'].user_id,'start_at':'2026-09-07T10:00:00','end_at':'2026-09-08T10:00:00'})
        self.assertEqual(reply.status_code,422)

    def test_concurrent_dispatchers_create_only_one_notification(self):
        record,flow=self.case();self.act(record,flow)
        with ThreadPoolExecutor(max_workers=2) as executor:list(executor.map(lambda _:ops.dispatch_events(self.factory),range(2)))
        self.assertEqual(self.count(Notification),1)
