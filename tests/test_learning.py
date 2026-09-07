import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import create_engine, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.learning import (decision_support, prior_case_support, record_decision, review_report,
                          validated_feedback_weights)
from app.models import Course, PortalUser, RequestDecision, RequestRecord, RequestReferral, RequestWorkflow
from app.portal_auth import Principal
from app.schemas import AnalyzeRequest, DecisionRequest
from app.workflow import record_analysis, request_detail


class LearningTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.pdf = Path(self.temp.name) / "course.pdf"
        self.pdf.write_bytes(b"synthetic current source")
        self.engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine, expire_on_commit=False)()
        self.principals = {}
        for role in ("EMPLOYEE", "NEEDS_ANALYST", "TECHNICAL_DESIGN", "ENGINEERING_DESIGN"):
            user = PortalUser(username=role.lower(), display_name=role, role=role,
                              password_salt="0" * 32, password_hash="0" * 64)
            self.db.add(user)
            self.db.flush()
            self.principals[role] = Principal(user.id, user.username, user.display_name, role)
        self.course = Course(code="TEST", name="Web eğitimi", pdf_path=str(self.pdf))
        self.db.add(self.course)
        self.db.commit()
        self.active = patch("app.learning.active_course_ids", return_value=[self.course.id])
        self.active.start()
        self.record, self.flow = self.make_request()

    def tearDown(self):
        self.active.stop()
        self.db.close()
        self.engine.dispose()
        self.temp.cleanup()

    def make_request(self, percent=80, need_type="EGITIM", canonical="web-api-learning"):
        row = RequestRecord(text="Web API test kapsamını öğrenmek istiyorum", topic="Web API", canonical_intent=canonical,
                            category="Yazılım Geliştirme ve Otomasyon", coverage="KISMEN_VAR")
        self.db.add(row)
        self.db.flush()
        result = {"request_id": row.id, "ai_mode": "PRIVATE_PROVIDER",
                  "classification": {"category_id": "SOFTWARE", "category": row.category, "subcategory_id": "SOFTWARE.WEB",
                                     "subcategory": "Web, API ve Uygulama Geliştirme", "topic": row.topic, "need_type": need_type,
                                     "risk_level": "NORMAL", "requirements": [{"id": "N1", "label": "API geliştirme"}, {"id": "N2", "label": "API testi"}]},
                  "coverage": {"status": "KISMEN_VAR", "fit_percent": percent, "missing_topics": ["API testi"], "policy_version": "test-policy"},
                  "courses": [{"course_id": self.course.id, "course_name": self.course.name,
                               "fit": {"percent": percent, "requirements": []}, "evidence": [{"content": "PRIVATE RAW EXCERPT"}]}]}
        record_analysis(self.db, row, result, self.principals["EMPLOYEE"].token_hash)
        self.db.commit()
        return row, self.db.get(RequestWorkflow, row.id)

    def decide(self, record=None, flow=None, role="NEEDS_ANALYST", **overrides):
        record, flow = record or self.record, flow or self.flow
        payload = {"outcome": "APPROVED", "expected_version": flow.version,
                   "reason": "Kapsam insan tarafından incelendi.", "training_need_confirmed": True}
        payload.update(overrides)
        return record_decision(self.db, record, flow, self.principals[role], DecisionRequest(**payload))

    def refer(self, department="ENGINEERING_DESIGN"):
        self.db.add(RequestReferral(request_id=self.record.id, department=department,
            analysis_summary="Eğitim ihtiyacı doğrulandı.", training_need_confirmed=True,
            analyst_id=self.principals["NEEDS_ANALYST"].user_id, active=True))
        self.flow.status = "REFERRED"
        self.db.commit()

    def test_decision_freezes_ai_actor_and_version_without_changing_original_analysis(self):
        original = self.flow.result_json
        result = self.decide()
        self.assertEqual(result["version"], 2)
        self.assertEqual(self.flow.result_json, original)
        decision = result["decisions"][0]
        self.assertEqual(decision["actual_subcategory_id"], "SOFTWARE.WEB")
        self.assertEqual(decision["actual_department"], "ENGINEERING_DESIGN")
        self.assertEqual(decision["actual_course_id"], self.course.id)
        self.assertEqual(decision["reviewer"]["id"], self.principals["NEEDS_ANALYST"].user_id)
        self.assertEqual(decision["original_ai"]["audit"]["analysis"]["ai_mode"], "PRIVATE_PROVIDER")
        self.assertEqual(decision["missing_topics"], ["API testi"])
        self.assertTrue(decision["created_at"].endswith("Z"))
        self.assertEqual(self.flow.status, "IN_REVIEW")

    def test_stale_decisions_are_rejected_without_duplicate_history(self):
        self.decide()
        with self.assertRaises(HTTPException) as error:
            self.decide(expected_version=1)
        self.assertEqual(error.exception.status_code, 409)
        self.assertEqual(len(self.db.scalars(select(RequestDecision)).all()), 1)

    def test_history_is_append_only_in_orm_and_bulk_sql(self):
        self.decide()
        row = self.db.scalar(select(RequestDecision))
        row.reason = "Attempt to rewrite history"
        with self.assertRaisesRegex(ValueError, "Karar geçmişi"):
            self.db.commit()
        self.db.rollback()
        for statement in ("UPDATE request_decisions SET reason='rewritten'", "DELETE FROM request_decisions"):
            with self.assertRaises(IntegrityError):
                self.db.execute(text(statement))
            self.db.rollback()
        self.assertEqual(self.db.scalar(select(RequestDecision)).reason, "Kapsam insan tarafından incelendi.")

    def test_guard_upgrade_covers_existing_table_without_changing_rows(self):
        from app.models import install_decision_guards
        self.decide()
        with self.engine.begin() as connection:
            connection.exec_driver_sql("DROP TRIGGER request_decisions_no_update")
            connection.exec_driver_sql("DROP TRIGGER request_decisions_no_delete")
        # Existing tables do not execute SQLAlchemy's after_create hook again.
        Base.metadata.create_all(self.engine)
        install_decision_guards(self.engine)
        install_decision_guards(self.engine)
        for statement in ("UPDATE request_decisions SET reason='rewritten'", "DELETE FROM request_decisions"):
            with self.assertRaises(IntegrityError):
                self.db.execute(text(statement))
            self.db.rollback()
        self.assertEqual(self.db.scalar(select(RequestDecision)).reason, "Kapsam insan tarafından incelendi.")

    def test_only_analyst_and_current_referred_department_can_review(self):
        for role, status in (("EMPLOYEE", 403), ("TECHNICAL_DESIGN", 404), ("ENGINEERING_DESIGN", 404)):
            with self.assertRaises(HTTPException) as error:
                self.decide(role=role)
            self.assertEqual(error.exception.status_code, status)
        self.refer()
        result = self.decide(role="ENGINEERING_DESIGN")
        self.assertTrue(result["permissions"]["can_review"])
        self.assertNotIn("PRIVATE", json.dumps(result))
        referral = self.db.get(RequestReferral, self.record.id)
        referral.department = "TECHNICAL_DESIGN"
        self.db.commit()
        with self.assertRaises(HTTPException) as error:
            self.decide(role="ENGINEERING_DESIGN")
        self.assertEqual(error.exception.status_code, 404)

    def test_employee_does_not_receive_internal_decisions_or_options(self):
        self.decide(reason="INTERNAL human review discussion")
        result = request_detail(self.db, self.record, self.flow)
        for hidden in ("decisions", "review_options", "INTERNAL", "PRIVATE", "learning_objectives", "prior_cases"):
            self.assertNotIn(hidden, json.dumps(result))
        self.assertFalse(result["permissions"]["can_review"])
        self.assertEqual(result["decision_support"]["action"], "ENRICH_COURSE")

    def test_approved_cannot_disguise_corrections_and_modified_requires_actual_change(self):
        with self.assertRaises(HTTPException) as error:
            self.decide(actual_subcategory_id="DATA.EXCEL")
        self.assertEqual(error.exception.status_code, 422)
        with self.assertRaises(HTTPException):
            self.decide(outcome="MODIFIED", actual_subcategory_id="SOFTWARE.WEB",
                        actual_department="ENGINEERING_DESIGN", actual_course_id=self.course.id)
        result = self.decide(outcome="MODIFIED", actual_subcategory_id="DATA.EXCEL",
                             actual_department="TECHNICAL_DESIGN", actual_course_id=self.course.id,
                             missing_topics=["Formül kullanımı"], excess_topics=["İleri ağ yönetimi"])
        self.assertIn("subcategory", result["decisions"][0]["changed_fields"])
        self.assertEqual(result["decisions"][0]["actual_category"], "Veri Analizi ve Raporlama")

    def test_repeated_review_is_one_vote_and_latest_rejection_revokes_feedback(self):
        self.decide()
        first = validated_feedback_weights(self.db, self.record.canonical_intent)
        self.decide()
        self.assertEqual(validated_feedback_weights(self.db, self.record.canonical_intent), first)
        self.assertEqual(first, {self.course.id: .01})
        self.decide(outcome="REJECTED", actual_course_id=self.course.id)
        self.assertEqual(validated_feedback_weights(self.db, self.record.canonical_intent), {})
        report = review_report(self.db, self.principals["NEEDS_ANALYST"])
        self.assertEqual(report["summary"]["decisions_total"], 3)
        self.assertEqual(report["summary"]["reviewed_requests"], 1)
        self.assertEqual(report["summary"]["rejected"], 1)

    def test_unconfirmed_human_need_and_changed_source_cannot_boost_retrieval(self):
        self.decide(outcome="MODIFIED", training_need_confirmed=False, actual_subcategory_id="SOFTWARE.WEB",
                    actual_department="ENGINEERING_DESIGN", actual_course_id=self.course.id)
        self.assertEqual(validated_feedback_weights(self.db, self.record.canonical_intent), {})
        self.decide(training_need_confirmed=True)
        self.assertTrue(validated_feedback_weights(self.db, self.record.canonical_intent))
        self.pdf.write_bytes(b"replacement PDF content")
        self.assertEqual(validated_feedback_weights(self.db, self.record.canonical_intent), {})
        self.pdf.unlink()
        with self.assertRaises(HTTPException) as error:
            self.decide()
        self.assertEqual(error.exception.status_code, 422)

    def test_changed_analysis_source_requires_fresh_assessment_before_approval(self):
        from app.indexing import fingerprint
        result = json.loads(self.flow.result_json)
        result["courses"][0]["evidence"][0]["source_hash"] = fingerprint(self.pdf)
        self.flow.result_json = json.dumps(result)
        self.db.commit()
        self.pdf.write_bytes(b"course changed after AI analysis")
        with self.assertRaises(HTTPException) as error:
            self.decide()
        self.assertEqual(error.exception.status_code, 409)
        self.assertEqual(len(self.db.scalars(select(RequestDecision)).all()), 0)
        # Disagreeing with stale AI is still auditable and never supplies a positive vote.
        self.decide(outcome="REJECTED")
        self.assertEqual(validated_feedback_weights(self.db, self.record.canonical_intent), {})

    def test_reporting_counts_latest_request_and_distinguishes_confirmed_repeated_needs(self):
        self.decide()
        self.decide()
        second, second_flow = self.make_request()
        self.decide(record=second, flow=second_flow, outcome="MODIFIED", actual_subcategory_id="SOFTWARE.WEB",
                    actual_department="ENGINEERING_DESIGN", actual_course_id=self.course.id,
                    training_need_confirmed=False, excess_topics=["İlgisiz kapsam"])
        report = review_report(self.db, self.principals["NEEDS_ANALYST"])
        self.assertEqual(report["summary"]["reviewed_requests"], 2)
        self.assertEqual(report["summary"]["decisions_total"], 3)
        self.assertEqual(report["summary"]["agreement_percent"], 50)
        self.assertEqual(report["repeated_needs"][0]["request_count"], 2)
        self.assertEqual(report["repeated_needs"][0]["confirmed_count"], 1)
        self.assertEqual(report["scope_gaps"][0]["count"], 2)
        self.assertEqual(report["excess_scope"][0]["topic"], "İlgisiz kapsam")
        self.assertFalse(report["learning"]["model_weights_trained"])
        self.assertFalse(report["learning"]["autonomous_decisions_enabled"])

    def test_report_scope_and_zero_denominator_are_safe(self):
        report = review_report(self.db, self.principals["TECHNICAL_DESIGN"])
        self.assertEqual(report["summary"]["total_requests"], 0)
        self.assertIsNone(report["summary"]["agreement_percent"])
        self.assertEqual(report["repeated_needs"], [])
        with self.assertRaises(HTTPException):
            review_report(self.db, self.principals["EMPLOYEE"])

    def test_report_keeps_analysis_and_department_stage_counts_separate(self):
        self.decide()
        self.refer()
        self.decide(role="ENGINEERING_DESIGN", outcome="REJECTED")
        report = review_report(self.db, self.principals["NEEDS_ANALYST"])
        self.assertEqual(report["summary"]["reviewed_requests"], 1)
        self.assertEqual(report["summary"]["rejected"], 1)
        by_role = {row["role"]: row for row in report["by_role"]}
        self.assertEqual(by_role["NEEDS_ANALYST"]["approved"], 1)
        self.assertEqual(by_role["ENGINEERING_DESIGN"]["rejected"], 1)

    def test_prior_case_category_department_votes_are_explicit_and_conflicts_visible(self):
        self.decide()
        second, second_flow = self.make_request()
        self.decide(record=second, flow=second_flow, outcome="MODIFIED", actual_subcategory_id="DATA.EXCEL",
                    actual_department="TECHNICAL_DESIGN", actual_course_id=self.course.id)
        support = prior_case_support(self.db, self.record.canonical_intent)
        self.assertEqual(support["sample_count"], 2)
        self.assertTrue(support["has_conflict"])
        self.assertEqual(len(support["category_votes"]), 2)
        self.assertEqual(len(support["department_votes"]), 2)
        self.assertEqual(prior_case_support(self.db, self.record.canonical_intent, exclude_request_id=second.id)["sample_count"], 1)

    def test_threshold_new_course_brief_and_non_training_routing(self):
        baseline = json.loads(self.flow.result_json)
        for percent, action in ((0, "NEW_COURSE"), (40, "NEW_COURSE"), (40.1, "ENRICH_COURSE"), (94, "ENRICH_COURSE")):
            baseline["coverage"]["fit_percent"] = percent
            support = decision_support(baseline, self.record.text)
            self.assertEqual(support["action"], action)
            if percent <= 40:
                self.assertIsNone(support["brief"]["existing_course"])
        baseline["coverage"].update(status="VAR", fit_percent=100, missing_topics=[])
        self.assertEqual(decision_support(baseline)["action"], "USE_COURSE")
        baseline["classification"]["need_type"] = "SUREC_ARAC"
        self.assertEqual(decision_support(baseline)["action"], "NON_TRAINING")
        baseline["classification"]["risk_level"] = "KRITIK"
        self.assertEqual(decision_support(baseline)["action"], "URGENT_REVIEW")
        baseline["classification"]["subcategory_id"] = "DATA.EXCEL"
        self.assertIsNone(decision_support(baseline)["suggested_department"]["id"])
        self.assertEqual(decision_support({})["action"], "CLARIFY")

    def test_invalid_topic_and_whitespace_requests_are_rejected(self):
        with self.assertRaises(ValidationError):
            AnalyzeRequest(text="   ")
        with self.assertRaises(HTTPException):
            self.decide(outcome="MODIFIED", missing_topics=["x" * 301])
        with self.assertRaises(HTTPException):
            self.decide(reason="          ")

    def test_decision_and_report_endpoints_preserve_permissions_and_version_contract(self):
        # Avoid the production database create_all side effect if main is first imported here.
        with patch.object(Base.metadata, "create_all"), patch("app.models.install_decision_guards"):
            from app.main import app
        from app.database import get_db
        from app.portal_auth import owner_session
        original_overrides = dict(app.dependency_overrides)
        app.dependency_overrides[get_db] = lambda: self.db
        app.dependency_overrides[owner_session] = lambda: self.principals["NEEDS_ANALYST"]
        client = TestClient(app)
        try:
            body = {"outcome": "APPROVED", "expected_version": 1, "reason": "API üzerinden insan doğrulaması.", "training_need_confirmed": True}
            response = client.post(f"/api/admin/requests/{self.record.id}/decisions", json=body)
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.json()["version"], 2)
            self.assertEqual(len(response.json()["decisions"]), 1)
            stale = client.post(f"/api/admin/requests/{self.record.id}/decisions", json=body)
            self.assertEqual(stale.status_code, 409)
            report = client.get("/api/admin/review-report")
            self.assertEqual(report.status_code, 200, report.text)
            self.assertEqual(report.json()["summary"]["reviewed_requests"], 1)
            app.dependency_overrides[owner_session] = lambda: self.principals["EMPLOYEE"]
            self.assertEqual(client.get("/api/admin/review-report").status_code, 403)
            self.assertEqual(client.post(f"/api/admin/requests/{self.record.id}/decisions", json=body).status_code, 403)
        finally:
            client.close()
            app.dependency_overrides.clear()
            app.dependency_overrides.update(original_overrides)


if __name__ == "__main__":
    unittest.main()
