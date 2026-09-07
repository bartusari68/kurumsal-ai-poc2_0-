"""Durability/versions use synthetic inputs, local SQLite and no external provider."""
import asyncio
import json
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app.models import (AnalysisRun, DecisionAnalysisLink, PortalUser, RequestDecision, RequestEvent,
    RequestRecord, RequestSubmission, RequestWorkflow, install_analysis_guards)
from app.portal_auth import Principal, owner_session
from app.schemas import AnalysisRetryRequest, DecisionRequest, WorkflowActionRequest
from app import analysis_pipeline as pipeline
from app.workflow import record_analysis, request_detail
from app.workflow_core import execute_action
from app.learning import record_decision, decision_history, review_report


def result(topic="Sentetik API ihtiyacı"):
    return {"classification": {"category": "Yazılım", "subcategory_id": "SOFTWARE.WEB", "topic": topic,
            "need_type": "EGITIM", "risk_level": "NORMAL", "canonical_intent": "synthetic-api",
            "requirements": [{"id": "N1", "label": "API testi"}]},
            "coverage": {"status": "YOK", "fit_percent": 0, "missing_topics": ["API testi"]}, "courses": []}


class DurableAnalysisTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.engine = create_engine("sqlite:///" + str(Path(self.folder.name) / "analysis.db"), connect_args={"check_same_thread": False})
        Base.metadata.create_all(self.engine)
        install_analysis_guards(self.engine)
        self.factory = sessionmaker(bind=self.engine, expire_on_commit=False, autoflush=False)
        self.db = self.factory()
        self.people = {}
        for name, role in (("employee", "EMPLOYEE"), ("other", "EMPLOYEE"), ("analyst", "NEEDS_ANALYST"), ("design", "TECHNICAL_DESIGN")):
            user = PortalUser(username=name, display_name=name, role=role, password_salt="0"*32, password_hash="0"*64)
            self.db.add(user)
            self.db.flush()
            self.people[name] = Principal(user.id, name, name, role)
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()
        self.folder.cleanup()

    def new(self, key="synthetic-initial-1"):
        return pipeline.persist_request(self.db, "Orijinal sentetik API talebim", self.people["employee"], key)

    async def execute(self, record, output=None, error=None):
        self.db.expire_all()
        run = pipeline.latest_run(self.db, record.id)
        evaluator = AsyncMock(side_effect=error) if error else AsyncMock(return_value=output or result())
        ok = await pipeline.execute_run(self.factory, run.id, evaluator)
        self.db.expire_all()
        return ok, pipeline.latest_run(self.db, record.id)

    def retry(self, record, flow, key="retry-operation-1", user="employee", version=None):
        return pipeline.request_analysis(self.db, record, flow, self.people[user], AnalysisRetryRequest(
            expected_version=flow.version if version is None else version, idempotency_key=key))

    def act(self, record, flow, code, user, note="Sentetik kapsam açıklaması"):
        return execute_action(self.db, record, flow, self.people[user], WorkflowActionRequest(
            action=code, expected_version=flow.version, note=note))

    async def test_saved_request_exists_before_any_model_call_and_success_completes_same_id(self):
        record, flow = self.new()
        with self.factory() as another:
            self.assertEqual(another.get(RequestRecord, record.id).text, record.text)
            self.assertEqual(pipeline.latest_run(another, record.id).status, "PENDING")
        ok, run = await self.execute(record)
        self.assertTrue(ok)
        self.assertEqual(run.status, "COMPLETED")
        self.assertIsNone(run.active_request_id)
        self.assertEqual(json.loads(run.result_json)["request_id"], record.id)
        self.assertEqual(self.db.scalar(select(func.count(RequestRecord.id))), 1)
        self.assertEqual(flow.status, "IN_REVIEW")

    async def test_failure_categories_retain_request_without_secrets(self):
        from app.ai import AIResponseError, AIUnavailableError
        from app.ai_errors import AIServiceError
        from app.indexing import IndexNotReadyError
        cases = [(AIUnavailableError("SECRET api-key /private/path"), "SERVICE_UNAVAILABLE"),
                 (httpx.ReadTimeout("SECRET timeout"), "TIMEOUT"),
                 (httpx.ConnectError("SECRET connection"), "SERVICE_UNAVAILABLE"),
                 (AIResponseError("SECRET invalid JSON"), "INVALID_RESPONSE"),
                 (AIServiceError("SECRET provider body", code="AI_RATE_LIMITED", component="analysis"), "RATE_LIMITED"),
                 (IndexNotReadyError({"complete": False, "documents": []}), "SOURCE_UNAVAILABLE"),
                 (RuntimeError("SECRET internal path"), "INTERNAL_FAILURE")]
        for i, (error, code) in enumerate(cases):
            with self.subTest(code=code):
                record, flow = self.new(key=f"synthetic-error-{i}")
                ok, run = await self.execute(record, error=error)
                self.assertFalse(ok)
                self.assertEqual((run.status, run.error_code), ("FAILED", code))
                self.assertEqual(self.db.get(RequestRecord, record.id).text, "Orijinal sentetik API talebim")
                detail = request_detail(self.db, record, flow)
                self.assertNotIn("SECRET", json.dumps(detail))
                self.assertEqual(detail["analysis_state"]["available_actions"][0]["code"], "RETRY")

    async def test_retry_is_same_request_and_same_operation_remains_idempotent_after_completion(self):
        record, flow = self.new()
        await self.execute(record, error=RuntimeError("synthetic"))
        failed = pipeline.latest_run(self.db, record.id)
        frozen = failed.error_code, failed.input_json, failed.completed_at
        first = self.retry(record, flow)
        second = self.retry(record, flow)
        self.assertEqual(first["analysis_state"]["latest_run"]["id"], second["analysis_state"]["latest_run"]["id"])
        await self.execute(record)
        self.retry(record, flow, version=1)
        runs = self.db.scalars(select(AnalysisRun).order_by(AnalysisRun.sequence)).all()
        self.assertEqual(len(runs), 2)
        self.assertEqual(runs[1].retry_of, failed.id)
        self.assertEqual((failed.error_code, failed.input_json, failed.completed_at), frozen)
        self.assertEqual(self.db.scalar(select(func.count(RequestRecord.id))), 1)

    async def test_pending_and_processing_prevent_second_active_run(self):
        record, flow = self.new()
        first = pipeline.latest_run(self.db, record.id)
        self.retry(record, flow)
        self.assertEqual(self.db.scalar(select(func.count(AnalysisRun.id))), 1)
        entered, release = asyncio.Event(), asyncio.Event()
        async def evaluator(db, source):
            entered.set()
            await release.wait()
            return result()
        task = asyncio.create_task(pipeline.execute_run(self.factory, first.id, evaluator))
        await entered.wait()
        self.db.expire_all()
        self.retry(record, flow, key="another-operation")
        self.assertEqual(self.db.scalar(select(func.count(AnalysisRun.id))), 1)
        release.set()
        await task

    async def test_concurrent_double_submit_has_one_receipt_request_and_run(self):
        def submit():
            with self.factory() as db:
                record, _ = pipeline.persist_request(db, "Eşzamanlı sentetik talep", self.people["employee"], "same-network-operation")
                return record.id
        with ThreadPoolExecutor(max_workers=2) as executor:
            first, second = executor.submit(submit), executor.submit(submit)
            self.assertEqual(first.result(), second.result())
        self.assertEqual(self.db.scalar(select(func.count(RequestRecord.id))), 1)
        self.assertEqual(self.db.scalar(select(func.count(RequestSubmission.id))), 1)
        self.assertEqual(self.db.scalar(select(func.count(AnalysisRun.id))), 1)

    async def test_same_submission_key_cannot_change_original_text(self):
        record, _ = self.new()
        with self.assertRaises(HTTPException) as conflict:
            pipeline.persist_request(self.db, "Farklı bir metin", self.people["employee"], "synthetic-initial-1")
        self.assertEqual(conflict.exception.status_code, 409)
        self.assertEqual(record.text, "Orijinal sentetik API talebim")

    async def test_extra_information_creates_version_and_preserves_original_and_first_result(self):
        record, flow = self.new()
        await self.execute(record)
        first = pipeline.latest_run(self.db, record.id)
        original, initial = record.text, flow.result_json
        self.act(record, flow, "REQUEST_INFO", "analyst")
        self.act(record, flow, "PROVIDE_INFO", "employee", "Ek bilgi: otomatik API testleri de gerekiyor.")
        next_run = pipeline.latest_run(self.db, record.id)
        self.assertEqual((next_run.sequence, next_run.trigger), (2, "EXTRA_INFO"))
        snapshot = json.loads(next_run.input_json)
        self.assertEqual(snapshot["original_request"], original)
        self.assertEqual(len(snapshot["additional_event_ids"]), 1)
        self.assertIn("otomatik API", pipeline.input_text(self.db, snapshot, record.id))
        self.assertEqual(snapshot["request_version"], flow.version)
        await self.execute(record, result("Ek bilgilerle güncel sonuç"))
        self.assertEqual(record.text, original)
        self.assertEqual(flow.result_json, initial)
        self.assertEqual(first.result_json, initial)
        self.assertEqual(request_detail(self.db, record, flow)["classification"]["topic"], "Ek bilgilerle güncel sonuç")

    async def test_failed_new_run_keeps_previous_success_visible_and_old_decision_frozen(self):
        record, flow = self.new()
        await self.execute(record)
        record_decision(self.db, record, flow, self.people["analyst"], DecisionRequest(
            outcome="APPROVED", expected_version=flow.version, reason="Sentetik kapsam insan tarafından doğrulandı."))
        old = self.db.scalar(select(RequestDecision))
        frozen = old.original_ai_json, old.created_at, old.request_version
        original_run = pipeline.latest_run(self.db, record.id)
        self.retry(record, flow)
        await self.execute(record, error=RuntimeError("synthetic"))
        detail = request_detail(self.db, record, flow, admin=True, role="NEEDS_ANALYST")
        state = detail["analysis_state"]
        self.assertEqual(state["latest_run"]["status"], "FAILED")
        self.assertEqual(state["latest_completed"]["id"], original_run.id)
        self.assertEqual(detail["classification"]["topic"], "Sentetik API ihtiyacı")
        self.assertEqual((old.original_ai_json, old.created_at, old.request_version), frozen)

    async def test_human_decisions_link_to_their_own_run_and_old_verdict_is_not_current(self):
        record, flow = self.new()
        await self.execute(record)
        def decide():
            return record_decision(self.db, record, flow, self.people["analyst"], DecisionRequest(
                outcome="APPROVED", expected_version=flow.version, reason="Sentetik kapsam insan tarafından doğrulandı."))
        decide()
        first = self.db.scalar(select(RequestDecision))
        initial = first.original_ai_json
        run_id = pipeline.latest_run(self.db, record.id).id
        self.retry(record, flow)
        await self.execute(record, result("Yeni sürüm"))
        report = review_report(self.db, self.people["analyst"])
        self.assertEqual(report["summary"]["pending_review"], 1)
        self.assertFalse(pipeline.decision_is_current(self.db, first, record, flow))
        decide()
        history = decision_history(self.db, record.id)
        self.assertEqual(history[1]["analysis_version"]["id"], run_id)
        self.assertNotEqual(history[0]["analysis_version"]["id"], run_id)
        self.assertEqual(first.original_ai_json, initial)

    async def test_changed_workflow_fences_out_inflight_result(self):
        record, flow = self.new()
        started, release = asyncio.Event(), asyncio.Event()
        async def evaluator(db, source):
            started.set()
            await release.wait()
            return result()
        task = asyncio.create_task(pipeline.execute_run(self.factory, pipeline.latest_run(self.db, record.id).id, evaluator))
        await started.wait()
        self.act(record, flow, "REQUEST_INFO", "analyst")
        release.set()
        self.assertFalse(await task)
        self.db.expire_all()
        run = pipeline.latest_run(self.db, record.id)
        self.assertEqual(run.error_code, "INPUT_CHANGED")
        self.assertEqual(flow.result_json, "{}")
        self.assertEqual(flow.status, "NEEDS_INFO")

    async def test_extra_info_supersedes_inflight_run_without_stale_publish(self):
        record, flow = self.new()
        started, release = asyncio.Event(), asyncio.Event()
        async def evaluator(db, source):
            started.set()
            await release.wait()
            return result("Eski girdi sonucu")
        task = asyncio.create_task(pipeline.execute_run(self.factory, pipeline.latest_run(self.db, record.id).id, evaluator))
        await started.wait()
        self.act(record, flow, "REQUEST_INFO", "analyst")
        self.act(record, flow, "PROVIDE_INFO", "employee", "Ek yeni sentetik kapsam bilgisi")
        release.set()
        await task
        await self.execute(record, result("Güncel girdi sonucu"))
        self.assertEqual(pipeline.current_result(self.db, record, flow)["classification"]["topic"], "Güncel girdi sonucu")
        self.assertEqual(self.db.scalar(select(func.count(RequestRecord.id))), 1)

    async def test_expired_processing_is_recovered_once_and_late_worker_cannot_finish_it(self):
        record, flow = self.new()
        run = pipeline.latest_run(self.db, record.id)
        self.db.execute(update(AnalysisRun).where(AnalysisRun.id == run.id).values(status="PROCESSING", lease_token="old-worker",
            started_at=datetime.utcnow()-timedelta(minutes=10), lease_expires_at=datetime.utcnow()-timedelta(seconds=1)))
        self.db.commit()
        pipeline.recover_expired(self.factory)
        count = self.db.scalar(select(func.count(RequestEvent.id)))
        pipeline.recover_expired(self.factory)
        self.db.expire_all()
        self.assertEqual(run.status, "FAILED")
        self.assertEqual(run.error_code, "INTERRUPTED")
        self.assertEqual(self.db.scalar(select(func.count(RequestEvent.id))), count)
        self.assertFalse(await pipeline.execute_run(self.factory, run.id, AsyncMock(return_value=result())))
        self.retry(record, flow)
        await self.execute(record)

    async def test_restart_worker_picks_persisted_pending_work(self):
        record, _ = self.new()
        with patch("app.services.compute_analysis", new=AsyncMock(return_value=result())):
            task = asyncio.create_task(pipeline.worker(self.factory))
            try:
                for _ in range(50):
                    await asyncio.sleep(.03)
                    self.db.expire_all()
                    if pipeline.latest_run(self.db, record.id).status == "COMPLETED":
                        break
                self.assertEqual(pipeline.latest_run(self.db, record.id).status, "COMPLETED")
            finally:
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)

    async def test_input_original_and_terminal_snapshots_are_database_immutable(self):
        record, _ = self.new()
        await self.execute(record)
        run = pipeline.latest_run(self.db, record.id)
        for statement in ("UPDATE requests SET text='forged'", "UPDATE analysis_runs SET result_json='{}'", "DELETE FROM analysis_runs"):
            with self.assertRaises(IntegrityError):
                self.db.execute(text(statement))
            self.db.rollback()
        self.assertEqual(self.db.get(AnalysisRun, run.id).status, "COMPLETED")

    async def test_existing_snapshot_uses_lazy_baseline_without_rewriting_legacy_history(self):
        record = RequestRecord(text="Eski özgün talep", topic="Eski konu")
        self.db.add(record)
        self.db.flush()
        record_analysis(self.db, record, result(), self.people["employee"].token_hash)
        self.db.commit()
        flow = self.db.get(RequestWorkflow, record.id)
        original = flow.result_json
        events = [(e.id, e.note, e.created_at) for e in self.db.scalars(select(RequestEvent))]
        self.assertEqual(pipeline.analysis_projection(self.db, record, flow, "EMPLOYEE")["latest_run"], None)
        self.retry(record, flow)
        imported = self.db.scalar(select(AnalysisRun).where(AnalysisRun.trigger == "IMPORTED"))
        self.assertEqual(imported.result_json, original)
        self.assertIsNone(imported.completed_at)
        await self.execute(record, result("Yeni analiz"))
        self.assertEqual(flow.result_json, original)
        for identifier, note, at in events:
            row = self.db.get(RequestEvent, identifier)
            self.assertEqual((row.note, row.created_at), (note, at))

    async def test_retry_authorization_visibility_and_stale_version(self):
        record, flow = self.new()
        await self.execute(record, error=RuntimeError("synthetic"))
        for user, status in (("other", 404), ("design", 404)):
            with self.assertRaises(HTTPException) as error:
                self.retry(record, flow, user=user)
            self.assertEqual(error.exception.status_code, status)
        with self.assertRaises(HTTPException) as error:
            self.retry(record, flow, version=999)
        self.assertEqual(error.exception.status_code, 409)

    async def test_database_rejects_duplicate_active_run_even_without_frontend(self):
        record, flow = self.new()
        self.db.add(AnalysisRun(request_id=record.id, sequence=2, status="PENDING", active_request_id=record.id,
            trigger="MANUAL", input_json="{}"))
        with self.assertRaises(IntegrityError):
            self.db.commit()
        self.db.rollback()

    async def test_concurrent_retry_creates_only_one_new_run(self):
        record, flow = self.new()
        await self.execute(record, error=RuntimeError("synthetic"))
        identifier, version = record.id, flow.version
        def retry(key):
            with self.factory() as db:
                try:
                    pipeline.request_analysis(db, db.get(RequestRecord, identifier), db.get(RequestWorkflow, identifier),
                        self.people["employee"], AnalysisRetryRequest(expected_version=version, idempotency_key=key))
                    return 202
                except HTTPException as error:
                    return error.status_code
        with ThreadPoolExecutor(max_workers=2) as executor:
            first, second = executor.submit(retry, "concurrent-retry-one"), executor.submit(retry, "concurrent-retry-two")
            self.assertTrue(all(code in (202, 409) for code in (first.result(), second.result())))
        self.assertEqual(self.db.scalar(select(func.count(AnalysisRun.id))), 2)
        self.assertEqual(self.db.scalar(select(func.count(AnalysisRun.id)).where(AnalysisRun.status.in_(pipeline.ACTIVE))), 1)

    async def test_execution_deadline_fails_durably_and_shutdown_cancels_safely(self):
        record, flow = self.new()
        entered = asyncio.Event()
        async def wait_forever(db, source):
            entered.set()
            await asyncio.Event().wait()
        with patch.object(pipeline, "EXECUTION_TIMEOUT", .05):
            await pipeline.execute_run(self.factory, pipeline.latest_run(self.db, record.id).id, wait_forever)
        self.db.expire_all()
        self.assertEqual(pipeline.latest_run(self.db, record.id).error_code, "TIMEOUT")
        self.retry(record, flow)
        entered.clear()
        task = asyncio.create_task(pipeline.execute_run(self.factory, pipeline.latest_run(self.db, record.id).id, wait_forever))
        await entered.wait()
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        self.db.expire_all()
        self.assertEqual(pipeline.latest_run(self.db, record.id).error_code, "INTERRUPTED")

    async def test_live_worker_renews_lease_and_second_executor_does_not_call_model(self):
        record, _ = self.new()
        identifier = pipeline.latest_run(self.db, record.id).id
        started = asyncio.Event()
        async def slow(db, source):
            started.set()
            await asyncio.sleep(.45)
            return result()
        with patch.object(pipeline, "LEASE_SECONDS", .3):
            task = asyncio.create_task(pipeline.execute_run(self.factory, identifier, slow))
            await started.wait()
            duplicate = AsyncMock(return_value=result())
            self.assertFalse(await pipeline.execute_run(self.factory, identifier, duplicate))
            duplicate.assert_not_awaited()
            await asyncio.sleep(.35)
            pipeline.recover_expired(self.factory)
            self.assertTrue(await task)
        self.db.expire_all()
        self.assertEqual(pipeline.latest_run(self.db, record.id).status, "COMPLETED")

    async def test_http_creation_is_accepted_while_provider_is_offline(self):
        from app.main import app
        previous = dict(app.dependency_overrides)
        def database():
            with self.factory() as db:
                yield db
        app.dependency_overrides[get_db] = database
        app.dependency_overrides[owner_session] = lambda: self.people["employee"]
        try:
            with patch("app.services.compute_analysis", new=AsyncMock(side_effect=RuntimeError("offline"))) as model:
                client = TestClient(app)
                body = {"text": "HTTP sentetik talep", "idempotency_key": "http-same-operation"}
                first, second = client.post('/api/requests/analyze', json=body), client.post('/api/requests/analyze', json=body)
                self.assertEqual(first.status_code, 202)
                self.assertEqual(first.json()["request_id"], second.json()["request_id"])
                model.assert_not_awaited()
                self.assertEqual(first.json()["analysis_state"]["latest_run"]["status"], "PENDING")
                self.assertFalse(first.json()["permissions"]["can_review"])
                client.close()
        finally:
            app.dependency_overrides.clear()
            app.dependency_overrides.update(previous)
