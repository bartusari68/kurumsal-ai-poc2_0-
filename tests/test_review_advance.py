"""Workflow integration tests use synthetic requests and an isolated SQLite database."""
import json
import unittest
from unittest.mock import patch

from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import event, func, select, text
from sqlalchemy.exc import IntegrityError

import test_learning
from app.learning import prior_case_support, record_decision, record_decision_and_advance
from app.models import RequestDecision, RequestEvent, RequestEventIdentity, RequestReferral, RequestWorkflow
from app.process import resolve_routing
from app.schemas import DecisionAdvanceRequest, DecisionRequest
from app.workflow import change_status, refer_request, request_detail, request_list


class ReviewAdvanceTests(unittest.TestCase):
    setUp = test_learning.LearningTests.setUp
    tearDown = test_learning.LearningTests.tearDown
    make_request = test_learning.LearningTests.make_request

    def advance(self, record=None, flow=None, role="NEEDS_ANALYST", **changes):
        record, flow = record or self.record, flow or self.flow
        values = {"outcome": "APPROVED", "reason": "Kapsam ve eğitim ihtiyacı doğrulandı.", "expected_version": flow.version, **changes}
        return record_decision_and_advance(self.db, record, flow, self.principals[role], DecisionAdvanceRequest(**values))

    def test_approval_derives_training_and_refers_in_one_version_without_second_confirmation(self):
        result = self.advance()
        self.assertEqual((result["status"], result["version"]), ("REFERRED", 2))
        self.assertTrue(result["decisions"][0]["training_need_confirmed"])
        self.assertEqual(result["referral"]["department"], "ENGINEERING_DESIGN")
        self.assertEqual(result["decisions"][0]["reason"], result["referral"]["analysis_summary"])
        self.assertEqual(result["process"]["current_owner"]["role"], "ENGINEERING_DESIGN")
        self.assertEqual(result["process"]["next_action"]["code"], "DESIGN_REVIEW")
        self.assertEqual(self.db.scalar(select(func.count(RequestDecision.id))), 1)

    def test_old_decision_endpoint_without_confirmation_remains_record_only(self):
        result = record_decision(self.db, self.record, self.flow, self.principals["NEEDS_ANALYST"],
            DecisionRequest(outcome="APPROVED", expected_version=1, reason="Kaynaklar ve ihtiyaç doğrulandı."))
        self.assertEqual(result["status"], "IN_REVIEW")
        self.assertTrue(result["decisions"][0]["training_need_confirmed"])
        self.assertIsNone(result["referral"])

    def test_unknown_target_is_requested_once_and_no_partial_decision_is_saved(self):
        result = json.loads(self.flow.result_json)
        result["classification"]["subcategory_id"] = "DATA.EXCEL"
        result["coverage"]["fit_percent"] = 0
        result["courses"] = []
        self.flow.result_json = json.dumps(result)
        self.db.commit()
        with self.assertRaises(HTTPException) as failure:
            self.advance()
        self.assertEqual(failure.exception.status_code, 422)
        self.assertEqual(self.db.scalar(select(func.count(RequestDecision.id))), 0)
        self.assertEqual(self.db.get(RequestWorkflow, self.record.id).version, 1)
        self.assertIsNone(self.db.get(RequestReferral, self.record.id))
        accepted = self.advance(routing_department="TECHNICAL_DESIGN")
        self.assertEqual(accepted["referral"]["department"], "TECHNICAL_DESIGN")
        self.assertEqual(accepted["decisions"][0]["outcome"], "APPROVED")
        self.assertEqual(accepted["decisions"][0]["original_ai"]["audit"]["advancement"]["routing"]["source"], "human_selection")

    def test_modified_category_routes_from_actual_human_decision(self):
        result = self.advance(outcome="MODIFIED", training_need_confirmed=True,
            actual_subcategory_id="OPERATIONS.MAINTENANCE", missing_topics=["Bakım uygulaması"])
        self.assertEqual(result["referral"]["department"], "TECHNICAL_DESIGN")
        self.assertEqual(result["decisions"][0]["actual_subcategory_id"], "OPERATIONS.MAINTENANCE")
        self.assertEqual(result["decisions"][0]["original_ai"]["classification"]["subcategory_id"], "SOFTWARE.WEB")

    def test_modified_explicit_department_is_used_without_repeated_selection(self):
        result = self.advance(outcome="MODIFIED", training_need_confirmed=True,
            actual_department="TECHNICAL_DESIGN")
        self.assertEqual(result["referral"]["department"], "TECHNICAL_DESIGN")

    def test_operational_assignment_is_retained_separately_from_ai_verdict_and_learned(self):
        result = self.advance(routing_department="TECHNICAL_DESIGN")
        self.assertEqual(result["decisions"][0]["outcome"], "APPROVED")
        self.assertEqual(result["decisions"][0]["actual_department"], "ENGINEERING_DESIGN")
        self.assertEqual(result["decisions"][0]["routing"]["department"], "TECHNICAL_DESIGN")
        self.assertEqual(result["routing"]["department"], "TECHNICAL_DESIGN")
        history = prior_case_support(self.db, self.record.canonical_intent)
        self.assertEqual(history["department_votes"][0]["id"], "TECHNICAL_DESIGN")

    def test_newer_active_referral_takes_precedence_over_older_human_destination(self):
        self.advance(routing_department="TECHNICAL_DESIGN")
        result = refer_request(self.db, self.record, self.flow, self.principals["NEEDS_ANALYST"],
            "ENGINEERING_DESIGN", "Yeni kapsam ile sorumlu birim güncellendi.", True, 2)
        self.assertEqual(result["routing"]["department"], "ENGINEERING_DESIGN")
        self.assertEqual(result["routing"]["source"], "active_referral")

    def test_active_referral_wins_when_windows_clock_returns_the_same_timestamp(self):
        self.advance(routing_department="TECHNICAL_DESIGN")
        latest = self.db.scalar(select(RequestDecision).order_by(RequestDecision.id.desc()))
        with patch("app.workflow.datetime") as clock:
            clock.utcnow.return_value = latest.created_at
            result = refer_request(self.db, self.record, self.flow, self.principals["NEEDS_ANALYST"],
                "ENGINEERING_DESIGN", "Yeni kapsam ile sorumlu birim güncellendi.", True, 2)
        self.assertEqual(result["routing"]["department"], "ENGINEERING_DESIGN")
        self.assertEqual(result["routing"]["source"], "active_referral")

    def test_full_existing_course_goes_to_plan_without_design_dropdown(self):
        result = json.loads(self.flow.result_json)
        result["classification"]["subcategory_id"] = "DATA.EXCEL"
        result["coverage"].update(status="VAR", fit_percent=97, missing_topics=[])
        self.flow.result_json = json.dumps(result)
        self.db.commit()
        result = self.advance()
        self.assertEqual(result["status"], "ACTION_PLANNED")
        self.assertIsNone(result["referral"])
        self.assertFalse(any(step["id"] == "design" and step["state"] == "pending" for step in result["process"]["steps"]))

    def test_nontraining_and_ambiguous_approval_do_not_invent_training_confirmation(self):
        for need_type, percent in (("SUREC_ARAC", 60), ("EGITIM", None), ("KRITIK_ICERIK", 80)):
            with self.subTest(need_type=need_type, percent=percent):
                record, flow = self.make_request(percent=percent, need_type=need_type)
                result = self.advance(record, flow)
                self.assertEqual(result["status"], "IN_REVIEW")
                self.assertFalse(result["decisions"][0]["training_need_confirmed"])
                self.assertIsNone(result["referral"])

    def test_partial_ai_match_with_no_extracted_gaps_still_needs_design_review(self):
        result = json.loads(self.flow.result_json)
        result["coverage"]["missing_topics"] = []
        self.flow.result_json = json.dumps(result)
        self.db.commit()
        accepted = self.advance()
        self.assertEqual(accepted["status"], "REFERRED")

    def test_human_can_explicitly_confirm_previously_ambiguous_training_need(self):
        record, flow = self.make_request(percent=None)
        result = self.advance(record, flow, outcome="MODIFIED", training_need_confirmed=True,
                              actual_department="ENGINEERING_DESIGN")
        self.assertEqual(result["status"], "REFERRED")
        self.assertIn("training_need_confirmed", result["decisions"][0]["changed_fields"])

    def test_reject_returns_to_analysis_and_revokes_prior_department_visibility(self):
        self.advance()
        result = self.advance(outcome="REJECTED", reason="İhtiyaç yanlış yorumlanmış; yeniden değerlendirme gerekiyor.")
        self.assertEqual(result["status"], "IN_REVIEW")
        self.assertFalse(result["referral"]["active"])
        self.assertEqual(result["process"]["current_owner"]["role"], "NEEDS_ANALYST")

    def test_version_conflict_cannot_duplicate_or_reassign_the_approved_request(self):
        self.advance()
        with self.assertRaises(HTTPException) as failure:
            self.advance(expected_version=1, routing_department="TECHNICAL_DESIGN")
        self.assertEqual(failure.exception.status_code, 409)
        self.assertEqual(self.db.scalar(select(func.count(RequestDecision.id))), 1)
        self.assertEqual(self.db.get(RequestReferral, self.record.id).department, "ENGINEERING_DESIGN")

    def test_commit_failure_rolls_back_decision_status_referral_and_actor_event(self):
        with patch.object(self.db, "commit", side_effect=RuntimeError("synthetic transaction failure")):
            with self.assertRaises(RuntimeError):
                self.advance()
        self.assertEqual(self.db.get(RequestWorkflow, self.record.id).version, 1)
        self.assertEqual(self.db.get(RequestWorkflow, self.record.id).status, "IN_REVIEW")
        self.assertIsNone(self.db.get(RequestReferral, self.record.id))
        self.assertEqual(self.db.scalar(select(func.count(RequestDecision.id))), 0)
        self.assertEqual(self.db.scalar(select(func.count(RequestEventIdentity.event_id))), 0)
        self.assertEqual(self.db.scalar(select(func.count(RequestEvent.id))), 1)

    def test_department_cannot_self_assign_even_after_referral(self):
        self.advance()
        with self.assertRaises(HTTPException) as failure:
            self.advance(role="ENGINEERING_DESIGN")
        self.assertEqual(failure.exception.status_code, 403)
        self.assertEqual(self.db.get(RequestWorkflow, self.record.id).version, 2)

    def test_missing_or_changed_course_source_blocks_atomic_advance(self):
        self.pdf.unlink()
        with self.assertRaises(HTTPException) as failure:
            self.advance()
        self.assertEqual(failure.exception.status_code, 422)
        self.assertEqual(self.db.get(RequestWorkflow, self.record.id).version, 1)
        self.assertEqual(self.db.scalar(select(func.count(RequestDecision.id))), 0)

    def test_named_timeline_preserves_creator_actor_chronology_and_unknown_organization(self):
        result = self.advance()
        process = result["process"]
        self.assertEqual(process["creator"]["id"], self.principals["EMPLOYEE"].user_id)
        self.assertFalse(process["organization"]["known"])
        self.assertIsNone(process["organization"]["name"])
        referral = next(item for item in process["timeline"] if item["kind"] == "referral")
        self.assertEqual(referral["actor"]["id"], self.principals["NEEDS_ANALYST"].user_id)
        self.assertEqual(referral["actor"]["display_name"], self.principals["NEEDS_ANALYST"].display_name)
        times = [entry["at"] for entry in process["timeline"]]
        self.assertEqual(times, sorted(times))
        # A later account rename cannot rewrite the original process actor.
        user = self.db.get(test_learning.PortalUser, self.principals["NEEDS_ANALYST"].user_id)
        user.display_name = "Changed current account name"
        self.db.commit()
        revised = request_detail(self.db, self.record, self.flow, admin=True, role="NEEDS_ANALYST")
        self.assertEqual(next(item for item in revised["process"]["timeline"] if item["kind"] == "referral")["actor"], referral["actor"])

    def test_status_changes_snapshot_session_actor_and_history_cannot_be_rewritten(self):
        result = change_status(self.db, self.record, self.flow, owner_hash=self.principals["NEEDS_ANALYST"].token_hash,
            admin=True, target="NEEDS_INFO", note="İş çıktısını açıklayın.", expected_version=1,
            role="NEEDS_ANALYST", principal=self.principals["NEEDS_ANALYST"])
        self.assertEqual(result["process"]["current_owner"]["role"], "EMPLOYEE")
        self.assertEqual(result["process"]["timeline"][-1]["actor"]["id"], self.principals["NEEDS_ANALYST"].user_id)
        for table in ("request_events", "request_event_identities"):
            with self.assertRaises(IntegrityError):
                self.db.execute(text("DELETE FROM " + table))
            self.db.rollback()

    def test_invalid_sort_is_rejected_and_oldest_sort_is_real(self):
        newer, _ = self.make_request()
        result = request_list(self.db, "", admin=True, role="NEEDS_ANALYST", sort="oldest", limit=1)
        self.assertEqual(result["items"][0]["request_id"], self.record.id)
        self.assertNotEqual(result["items"][0]["request_id"], newer.id)
        with self.assertRaises(HTTPException) as failure:
            request_list(self.db, "", admin=True, role="NEEDS_ANALYST", sort="unsupported")
        self.assertEqual(failure.exception.status_code, 422)

    def test_list_and_detail_share_action_owner_across_actual_workflow_states(self):
        analyst = self.principals["NEEDS_ANALYST"]
        employee = self.principals["EMPLOYEE"]

        def assert_alignment(expected_role, expected_action):
            detail = request_detail(self.db, self.record, self.flow, admin=True, role=analyst.role)
            self.assertEqual(detail["process"]["current_owner"]["role"], expected_role)
            self.assertEqual(detail["process"]["next_action"]["code"], expected_action)
            for principal, admin in ((analyst, True), (employee, False)):
                listed = request_list(self.db, principal.token_hash, admin=admin, role=principal.role)
                row = next(item for item in listed["items"] if item["request_id"] == self.record.id)
                self.assertEqual(row["current_owner"], detail["process"]["current_owner"])
                self.assertEqual(row["next_action"], detail["process"]["next_action"])
                self.assertNotIn("PRIVATE", json.dumps(row))

        # Actual full-course approval has no department referral: the analyst owns delivery.
        result = json.loads(self.flow.result_json)
        result["coverage"].update(status="VAR", fit_percent=97, missing_topics=[])
        self.flow.result_json = json.dumps(result)
        self.db.commit()
        self.advance()
        with self.subTest(stage="analyst_plan"):
            assert_alignment("NEEDS_ANALYST", "DELIVER_SOLUTION")

        # Subsequent explicit design assignment retains that department through planning.
        refer_request(self.db, self.record, self.flow, analyst, "TECHNICAL_DESIGN",
                      "Ek tasarım kapsamı için birim görevlendirildi.", True, self.flow.version)
        designer = self.principals["TECHNICAL_DESIGN"]
        for status, expected_role, expected_action in (("ACTION_PLANNED", "TECHNICAL_DESIGN", "DELIVER_SOLUTION"),
                                                      ("RESOLVED", None, "COMPLETE")):
            change_status(self.db, self.record, self.flow, owner_hash=designer.token_hash, admin=True,
                          target=status, note="Sentetik süreç adımı güncellendi.", expected_version=self.flow.version,
                          role=designer.role, principal=designer)
            assert_alignment(expected_role, expected_action)
        change_status(self.db, self.record, self.flow, owner_hash=analyst.token_hash, admin=True,
                      target="IN_REVIEW", note="Ek ihtiyaç ile yeniden açıldı.", expected_version=self.flow.version,
                      role=analyst.role, principal=analyst)
        change_status(self.db, self.record, self.flow, owner_hash=analyst.token_hash, admin=True,
                      target="NEEDS_INFO", note="Ek bilgi bekleniyor.", expected_version=self.flow.version,
                      role=analyst.role, principal=analyst)
        assert_alignment("EMPLOYEE", "PROVIDE_INFO")

    def test_list_action_projection_loads_operational_fields_without_decision_audit(self):
        self.advance()
        statements = []

        def record_query(connection, cursor, statement, parameters, context, many):
            statements.append(statement.lower())

        event.listen(self.engine, "before_cursor_execute", record_query)
        try:
            listed = request_list(self.db, self.principals["NEEDS_ANALYST"].token_hash, admin=True, role="NEEDS_ANALYST")
        finally:
            event.remove(self.engine, "before_cursor_execute", record_query)
        self.assertEqual(listed["items"][0]["current_owner"]["role"], "ENGINEERING_DESIGN")
        self.assertFalse(any(table in statement for statement in statements
                             for table in ("original_ai_json", "request_event_identities", "request_event_actions")))

    def test_atomic_api_preserves_role_scope_identity_privacy_and_query_validation(self):
        # Importing the application must never initialize the real database in tests.
        with patch.object(test_learning.Base.metadata, "create_all"), patch("app.models.install_decision_guards"):
            from app.main import app
        from app.database import get_db
        from app.portal_auth import owner_session
        original = dict(app.dependency_overrides)
        app.dependency_overrides[get_db] = lambda: self.db
        principal = self.principals["EMPLOYEE"]
        app.dependency_overrides[owner_session] = lambda: principal
        client = TestClient(app)
        path = f"/api/admin/requests/{self.record.id}/review-and-advance"
        body = {"outcome": "APPROVED", "expected_version": 1, "reason": "API üzerinden kapsam doğrulaması."}
        try:
            self.assertEqual(client.post(path, json=body).status_code, 403)
            principal = self.principals["ENGINEERING_DESIGN"]
            self.assertEqual(client.post(path, json=body).status_code, 403)
            self.assertEqual(client.get(f"/api/admin/requests/{self.record.id}").status_code, 404)
            principal = self.principals["NEEDS_ANALYST"]
            approved = client.post(path, json=body)
            self.assertEqual(approved.status_code, 200, approved.text)
            self.assertEqual(approved.json()["status"], "REFERRED")
            self.assertEqual(client.post(path, json=body).status_code, 409)
            self.assertEqual(client.get("/api/admin/requests?sort=oldest").status_code, 200)
            self.assertEqual(client.get("/api/admin/requests?sort=unsafe").status_code, 422)
            principal = self.principals["TECHNICAL_DESIGN"]
            self.assertEqual(client.get(f"/api/admin/requests/{self.record.id}").status_code, 404)
            principal = self.principals["ENGINEERING_DESIGN"]
            department = client.get(f"/api/admin/requests/{self.record.id}")
            self.assertEqual(department.status_code, 200, department.text)
            self.assertNotIn("PRIVATE", department.text)
            self.assertNotIn("audit", department.json()["decisions"][0]["original_ai"])
            self.assertFalse(department.json()["permissions"]["can_review_and_advance"])
            self.assertEqual(department.json()["process"]["creator"]["id"], self.principals["EMPLOYEE"].user_id)
            self.assertEqual(client.post(path, json={**body, "expected_version": 2}).status_code, 403)
            principal = self.principals["EMPLOYEE"]
            employee = client.get(f"/api/requests/{self.record.id}")
            self.assertEqual(employee.status_code, 200)
            self.assertNotIn("PRIVATE", employee.text)
            self.assertNotIn("decisions", employee.json())
            self.assertNotIn("review_options", employee.json())
            self.assertEqual(client.get("/api/requests/mine?sort=oldest").status_code, 200)
            self.assertEqual(client.get("/api/requests/mine?sort=unsafe").status_code, 422)
        finally:
            client.close()
            app.dependency_overrides.clear()
            app.dependency_overrides.update(original)


if __name__ == "__main__":
    unittest.main()
