"""Enterprise workflow behavior with synthetic records and isolated SQLite."""
import json
import unittest
from datetime import date, datetime, timedelta
from unittest.mock import patch
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
import test_learning
from app import workflow_policy as policy
from app.models import (PortalUser, RequestAssignment, RequestDecision, RequestEvent,
    RequestEventAction, RequestRecord, RequestSolutionPlan, UserOrganization)
from app.workflow_core import execute_action
from app.workflow import owned_request, request_detail, request_list, refer_request
from app.learning import record_decision, record_decision_and_advance
from app.schemas import DecisionAdvanceRequest, DecisionRequest, WorkflowActionRequest


class WorkflowCoreTests(unittest.TestCase):
    setUp = test_learning.LearningTests.setUp
    tearDown = test_learning.LearningTests.tearDown
    make_request = test_learning.LearningTests.make_request

    def act(self, action, role="NEEDS_ANALYST", **values):
        return execute_action(self.db, self.record, self.flow, self.principals[role], WorkflowActionRequest(
            **{"action": action, "expected_version": self.flow.version, "note": "Sentetik süreç açıklaması", **values}))

    def refer(self):
        return refer_request(self.db, self.record, self.flow, self.principals["NEEDS_ANALYST"],
            "ENGINEERING_DESIGN", "Eğitim ihtiyacı incelendi ve doğrulandı.", True, self.flow.version)

    def plan(self, **values):
        return self.act("SAVE_PLAN", "ENGINEERING_DESIGN", summary="Uygulamalı API eğitimi ve sonuç doğrulaması.",
            responsible_unit="ENGINEERING_DESIGN", **values)

    def test_employee_and_analyst_cannot_skip_review_or_close_unplanned_request(self):
        for code, role in (("RESOLVE", "EMPLOYEE"), ("RESOLVE", "NEEDS_ANALYST"),
                           ("REQUEST_INFO", "EMPLOYEE"), ("SAVE_PLAN", "NEEDS_ANALYST"),
                           ("REFER", "EMPLOYEE"), ("ASSIGN", "EMPLOYEE")):
            with self.subTest(code=code, role=role), self.assertRaises(HTTPException) as error:
                self.act(code, role)
            self.assertEqual(error.exception.status_code, 422)
        self.assertEqual(self.flow.version, 1)
        self.assertEqual(len(self.db.scalars(select(RequestEvent)).all()), 1)

    def test_referred_plan_complete_reopen_has_real_events_and_preserves_ai(self):
        original = self.flow.result_json
        self.refer()
        saved = self.plan(target_date=date(2030, 1, 4))
        self.assertEqual(saved["status"], "ACTION_PLANNED")
        self.assertEqual(saved["process"]["plan"]["target_date"], "2030-01-04")
        self.assertEqual(saved["process"]["plan"]["created_by"]["id"], self.principals["ENGINEERING_DESIGN"].user_id)
        completed = self.act("RESOLVE", "EMPLOYEE")
        self.assertEqual(completed["process"]["plan"]["state"], "completed")
        self.assertEqual(completed["process"]["available_actions"][0]["code"], "REOPEN")
        self.act("REOPEN", "EMPLOYEE")
        self.assertEqual(self.flow.result_json, original)
        self.assertEqual(self.db.get(RequestSolutionPlan, self.record.id).state, "superseded")
        with self.assertRaises(HTTPException):
            self.act("RESOLVE", "EMPLOYEE")
        actions = self.db.scalars(select(RequestEventAction)).all()
        self.assertIn("PLAN_CREATED", [event.action for event in actions])
        close = next(event for event in actions if event.action == "RESOLVE")
        self.assertEqual((close.from_status, close.to_status), ("ACTION_PLANNED", "RESOLVED"))
        self.assertEqual(json.loads(close.details_json)["plan"]["after"]["state"], "completed")

    def test_plan_edit_keeps_original_creator_and_frozen_before_after(self):
        self.refer()
        self.plan()
        plan = self.db.get(RequestSolutionPlan, self.record.id)
        original_creator, original_time = plan.created_by, plan.created_at
        self.act("SAVE_PLAN", "ENGINEERING_DESIGN", summary="Güncellenmiş kapsam ve uygulama çıktıları.", responsible_unit="ENGINEERING_DESIGN")
        self.assertEqual((plan.created_by, plan.created_at), (original_creator, original_time))
        row = self.db.scalar(select(RequestEventAction).where(RequestEventAction.action == "PLAN_UPDATED"))
        audit = json.loads(row.details_json)
        self.assertNotEqual(audit["before"]["summary"], audit["after"]["summary"])
        with self.assertRaises(IntegrityError):
            self.db.execute(text("DELETE FROM request_event_actions"))
            self.db.commit()
        self.db.rollback()

    def test_assignment_validates_real_unit_users_and_revokes_on_rerouting(self):
        self.refer()
        with self.assertRaises(HTTPException):
            self.act("ASSIGN", assignee_id=self.principals["TECHNICAL_DESIGN"].user_id)
        user_id = self.principals["ENGINEERING_DESIGN"].user_id
        assigned = self.act("ASSIGN", assignee_id=user_id)
        self.assertEqual(assigned["process"]["assignee"]["id"], user_id)
        items = request_list(self.db, self.principals["ENGINEERING_DESIGN"].token_hash,
            admin=True, role="ENGINEERING_DESIGN", user_id=user_id, view="assigned")
        self.assertEqual(items["total"], 1)
        self.assertIn("assigned", [item["id"] for item in items["queue_views"]])
        refer_request(self.db, self.record, self.flow, self.principals["NEEDS_ANALYST"], "TECHNICAL_DESIGN",
            "Güncel tasarım hedefi bu birimdir.", True, self.flow.version)
        self.assertIsNone(self.db.get(RequestAssignment, self.record.id).assignee_id)
        self.assertEqual(request_list(self.db, "", admin=True, role="ENGINEERING_DESIGN", user_id=user_id, view="assigned")["total"], 0)
        with self.assertRaises(HTTPException) as error:
            owned_request(self.db, self.record.id, "", admin=True, role="ENGINEERING_DESIGN")
        self.assertEqual(error.exception.status_code, 404)

    def test_stale_plan_and_assignment_do_not_append_events_or_change_owner(self):
        self.refer()
        previous = self.flow.version
        self.plan()
        events = len(self.db.scalars(select(RequestEvent)).all())
        with self.assertRaises(HTTPException) as error:
            self.act("ASSIGN", expected_version=previous, assignee_id=self.principals["ENGINEERING_DESIGN"].user_id)
        self.assertEqual(error.exception.status_code, 409)
        self.assertEqual(len(self.db.scalars(select(RequestEvent)).all()), events)
        self.assertIsNone(self.db.get(RequestAssignment, self.record.id).assignee_id)

    def test_database_version_lock_rejects_a_stale_independent_session(self):
        from sqlalchemy.orm import Session
        from app.models import RequestWorkflow
        with Session(self.engine, expire_on_commit=False) as second:
            stale_record = second.get(RequestRecord, self.record.id)
            stale_flow = second.get(RequestWorkflow, self.record.id)
            self.act("ASSIGN", assignee_id=self.principals["NEEDS_ANALYST"].user_id)
            with self.assertRaises(HTTPException) as error:
                execute_action(second, stale_record, stale_flow, self.principals["NEEDS_ANALYST"],
                    WorkflowActionRequest(action="ASSIGN", expected_version=1, note="Eski ekranın işlem isteği"))
            self.assertEqual(error.exception.status_code, 409)
        self.db.expire_all()
        self.assertEqual(self.db.get(RequestAssignment, self.record.id).assignee_id, self.principals["NEEDS_ANALYST"].user_id)

    def test_unknown_and_inactive_assignees_are_rejected(self):
        for user_id in (99999, self.principals["EMPLOYEE"].user_id):
            with self.assertRaises(HTTPException):
                self.act("ASSIGN", assignee_id=user_id)
        user = self.db.get(PortalUser, self.principals["NEEDS_ANALYST"].user_id)
        user.active = False
        self.db.commit()
        with self.assertRaises(HTTPException):
            self.act("ASSIGN", assignee_id=user.id)

    def test_assigned_filter_correlates_each_requests_department_independently(self):
        self.refer()
        self.act("ASSIGN", assignee_id=self.principals["ENGINEERING_DESIGN"].user_id)
        first_id = self.record.id
        self.record, self.flow = self.make_request()
        refer_request(self.db, self.record, self.flow, self.principals["NEEDS_ANALYST"],
            "TECHNICAL_DESIGN", "İkinci sentetik talep farklı birime ait.", True, 1)
        self.act("ASSIGN", assignee_id=self.principals["TECHNICAL_DESIGN"].user_id)
        for role, identifier in (("ENGINEERING_DESIGN", first_id), ("TECHNICAL_DESIGN", self.record.id)):
            user = self.principals[role]
            listed = request_list(self.db, user.token_hash, admin=True, role=role, user_id=user.user_id, view="assigned")
            self.assertEqual([row["request_id"] for row in listed["items"]], [identifier])

    def test_org_is_nullable_and_employee_unit_is_never_a_routing_destination(self):
        employee = self.principals["EMPLOYEE"]
        self.assertFalse(request_detail(self.db, self.record, self.flow)["process"]["organization"]["known"])
        self.db.add(UserOrganization(user_id=employee.user_id, organization="Sentetik kurum", directorate="Test müdürlüğü",
                                     unit="Test çalışan birimi", chiefdom="Test şefliği", source="test"))
        self.db.commit()
        result = self.refer()
        self.assertEqual(result["process"]["organization"]["unit"], "Test çalışan birimi")
        self.assertEqual(result["referral"]["department"], "ENGINEERING_DESIGN")

    def test_aging_uses_events_and_sla_is_unset_unless_explicitly_configured(self):
        self.refer()
        result = request_detail(self.db, self.record, self.flow)
        age = result["process"]["aging"]
        self.assertIsNotNone(age["current_stage_seconds"])
        self.assertIsNone(age["sla"])
        with patch.dict(policy.SLA_TARGETS, {("REFERRED", "ENGINEERING_DESIGN"): {"target_seconds": 1}}), patch("app.workflow_core.utc_now") as clock:
            clock.return_value = __import__("app.time_policy", fromlist=["utc_now"]).utc_now() + timedelta(minutes=2)
            overdue = request_detail(self.db, self.record, self.flow)["process"]["aging"]["sla"]
            self.assertEqual(overdue["state"], "overdue")

    def test_additional_info_preserves_original_and_returns_to_review_without_fake_analysis(self):
        original = self.record.text, self.flow.result_json
        self.act("REQUEST_INFO")
        self.act("PROVIDE_INFO", "EMPLOYEE", note="Ek bilgi: gerçek çalışma örneği gerekiyor.")
        self.assertEqual((self.record.text, self.flow.result_json), original)
        self.assertEqual(self.flow.status, "IN_REVIEW")
        self.assertTrue(self.db.scalar(select(RequestEventAction).where(RequestEventAction.action == "PROVIDE_INFO")))

    def test_legacy_is_readable_and_explicitly_activated_without_modifying_source(self):
        legacy = RequestRecord(text="Önceki sentetik kayıt", topic="Geçmiş talep", ai_reason="Eski YZ açıklaması")
        self.db.add(legacy)
        self.db.commit()
        before = legacy.text, legacy.ai_reason, legacy.created_at
        result = request_detail(self.db, legacy, None, admin=True, role="NEEDS_ANALYST")
        self.assertEqual(result["status"], "LEGACY")
        self.assertIsNone(result["process"]["plan"])
        saved = execute_action(self.db, legacy, None, self.principals["NEEDS_ANALYST"],
            WorkflowActionRequest(action="START_REVIEW", expected_version=0, note="Önceki kayıt incelemeye alındı."))
        self.assertEqual(saved["status"], "IN_REVIEW")
        self.assertEqual((legacy.text, legacy.ai_reason, legacy.created_at), before)

    def test_review_history_survives_resolution_and_cannot_be_changed_when_closed(self):
        record_decision(self.db, self.record, self.flow, self.principals["NEEDS_ANALYST"],
            DecisionRequest(outcome="APPROVED", expected_version=1, reason="İhtiyaç ve kaynaklar incelendi."))
        original = self.db.scalar(select(RequestDecision)).original_ai_json
        self.act("SAVE_PLAN", summary="Onaylı ihtiyaca yönelik çözüm planı.", responsible_unit="NEEDS_ANALYST")
        closed = self.act("RESOLVE")
        self.assertEqual(len(closed["decisions"]), 1)
        with self.assertRaises(HTTPException):
            record_decision(self.db, self.record, self.flow, self.principals["NEEDS_ANALYST"],
                DecisionRequest(outcome="REJECTED", expected_version=self.flow.version, reason="Kapalı kayıt değiştirilemez."))
        self.assertEqual(self.db.scalar(select(RequestDecision)).original_ai_json, original)

    def test_api_manipulation_and_old_status_adapter_have_same_policy(self):
        from app.main import app
        from app.database import get_db
        from app.portal_auth import owner_session
        original = dict(app.dependency_overrides)
        app.dependency_overrides[get_db] = lambda: self.db
        app.dependency_overrides[owner_session] = lambda: self.principals["EMPLOYEE"]
        try:
            with patch("app.main.ensure_admin_credentials"), TestClient(app) as client:
                path = f"/api/requests/{self.record.id}"
                self.assertEqual(client.post(path + '/actions', json={"action": "ASSIGN", "expected_version": 1, "note": "Manipülasyon"}).status_code, 422)
                self.assertEqual(client.patch(path + '/status', json={"status": "RESOLVED", "expected_version": 1, "note": "Erken kapatma"}).status_code, 422)
                self.assertEqual(client.post('/api/admin/requests/'+str(self.record.id)+'/actions', json={"action": "REQUEST_INFO", "expected_version": 1, "note": "Manipülasyon"}).status_code, 403)
        finally:
            app.dependency_overrides.clear()
            app.dependency_overrides.update(original)
