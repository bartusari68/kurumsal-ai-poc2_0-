import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.ai import AIClient, AIUnavailableError, AIResponseError
from app.ai_errors import AIServiceError
from app.main import app
from app.indexing import IndexNotReadyError
from app.portal_auth import owner_session, require_admin, require_analyst, Principal


class ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from sqlalchemy.pool import StaticPool
        from app.database import Base, get_db
        from app.models import PortalUser
        cls.engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(cls.engine)
        cls.factory = sessionmaker(bind=cls.engine, expire_on_commit=False)
        def database():
            with cls.factory() as db:
                yield db
        app.dependency_overrides[get_db] = database
        with cls.factory() as db:
            db.add(PortalUser(id=900, username="test", display_name="Test", role="EMPLOYEE", password_salt="0"*32, password_hash="0"*64))
            db.commit()
        cls.client = TestClient(app)
        app.dependency_overrides[owner_session] = lambda: Principal(900, 'test', 'Test', 'EMPLOYEE')
        app.dependency_overrides[require_admin] = lambda: Principal(901, 'analyst', 'Analyst', 'NEEDS_ANALYST')
        app.dependency_overrides[require_analyst] = lambda: Principal(901, 'analyst', 'Analyst', 'NEEDS_ANALYST')

    @classmethod
    def tearDownClass(cls):
        app.dependency_overrides.clear()
        cls.client.close()
        cls.engine.dispose()

    def test_root_serves_current_interface(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("TUSAŞ | Kurumsal Öğrenme ve Yapay Zekâ", response.text)
        self.assertIn("aiConnectionBadge", response.text)
        self.assertIn('/static/css/platform.css', response.text)
        self.assertIn('/static/js/app.js', response.text)
        self.assertNotIn('base64,', response.text)

    def test_brand_assets_are_served_locally(self):
        for path in ("css/platform.css", "js/app.js", "js/i18n-tr.js",
                     "assets/brand/logo-white.png", "assets/brand/emblem.svg"):
            with self.subTest(path=path):
                self.assertEqual(self.client.get('/static/'+path).status_code, 200)

    def test_health_reports_verified_connection(self):
        fake_settings = SimpleNamespace(
            openrouter_api_key="test-key",
            ai_mode="openrouter",
            llm_model="test-llm",
            embedding_model="test-embedding",
            rerank_model="test-rerank",
        )
        with patch("app.main.settings", fake_settings), patch(
            "app.main.ai_client.healthcheck", new=AsyncMock(return_value={"ai_status": "connected", "components": {"analysis": "connected", "embedding": "connected", "rerank": "connected"}})
        ):
            response = self.client.get("/api/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["ai_status"], "connected")

    def test_health_exposes_quota_even_when_application_is_healthy(self):
        state = {"ai_status": "quota", "detail": "Daily quota exceeded", "quota_remaining": 0}
        with patch("app.main.ai_client.healthcheck", new=AsyncMock(return_value=state)) as mocked:
            response = self.client.get("/api/health?refresh=true")
        self.assertEqual(response.json()["status"], "ok")
        self.assertEqual(response.json()["ai_status"], "quota")
        mocked.assert_awaited_once_with(force=True)

    def analyzed(self, *, error=None, result=None):
        from app.analysis_pipeline import execute_run
        response = self.client.post("/api/requests/analyze", json={"text": "Synthetic test"})
        self.assertEqual(response.status_code, 202)
        payload = response.json()
        self.assertEqual(payload["analysis_state"]["latest_run"]["status"], "PENDING")
        evaluator = AsyncMock(side_effect=error) if error else AsyncMock(return_value=result)
        asyncio.run(execute_run(self.factory, payload["analysis_state"]["latest_run"]["id"], evaluator))
        return self.client.get('/api/requests/'+str(payload['request_id']))

    def test_analyze_quota_is_not_a_generic_server_connection_error(self):
        error = AIServiceError("PRIVATE quota", code="AI_DAILY_QUOTA_EXCEEDED", component="analysis", status_code=429, ai_status="quota")
        response = self.analyzed(error=error)
        run = response.json()["analysis_state"]["latest_run"]
        self.assertEqual(run["status"], "FAILED")
        self.assertEqual(run["error_code"], "RATE_LIMITED")
        self.assertIn("kullanım sınırı", run["error_message"])
        self.assertNotIn("PRIVATE", response.text)

    def test_analyze_endpoint_returns_service_result(self):
        expected = {"classification": {"category": "Kalite ve Süreç"}, "coverage": {"status": "YOK", "retrieval_score": 0.0}, "courses": []}
        response = self.analyzed(result=expected)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "IN_REVIEW")
        self.assertEqual(response.json()["analysis_state"]["latest_run"]["status"], "COMPLETED")
        self.assertNotIn("ai_mode", response.json())
        self.assertNotIn("retrieval_score", response.json()["coverage"])

    def test_invalid_analysis_response_is_distinct_and_does_not_expose_internal_details(self):
        response = self.analyzed(error=AIResponseError("PRIVATE model output"))
        run = response.json()["analysis_state"]["latest_run"]
        self.assertEqual(run["status"], "FAILED")
        self.assertEqual(run["error_code"], "INVALID_RESPONSE")
        self.assertIn("yanıtı doğrulanamadı", run["error_message"])
        self.assertNotIn("PRIVATE", response.text)

    def test_ai_client_does_not_generate_fake_result_without_key(self):
        client = AIClient()
        client.api_key = ""
        with self.assertRaises(AIUnavailableError):
            asyncio.run(client.classify_request("sentetik talep"))

    def test_incomplete_index_is_a_failed_analysis_with_a_retained_request(self):
        response = self.analyzed(error=IndexNotReadyError({"complete": False, "error_count": 1, "documents": []}))
        self.assertEqual(response.json()["analysis_state"]["latest_run"]["error_code"], "SOURCE_UNAVAILABLE")
        self.assertNotIn("document_index", response.json())

    def test_folder_sync_is_started_in_background(self):
        with patch("app.main.start_sync", return_value={"running": True}) as start:
            response = self.client.post("/api/documents/sync")
        self.assertEqual(response.status_code, 202)
        self.assertTrue(response.json()["accepted"])
        start.assert_called_once()

    def test_index_status_hides_internal_hash_and_path_key(self):
        report = {"complete": True, "documents": [{"file": "test.pdf", "status": "ready", "_key": "internal", "_hash": "secret", "_path": "internal-path"}]}
        with patch("app.main.index_status", return_value=report):
            response = self.client.get("/api/documents/status")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["documents"], [{"file": "test.pdf", "status": "ready"}])

    def test_document_status_is_paginated_and_never_lists_deleted_sources(self):
        report = {"complete": True, "missing_count": 1, "documents": [
            {"file": f"{i:04d}.pdf", "status": "ready"} for i in range(1000)
        ] + [{"file": "deleted.pdf", "status": "missing"}]}
        with patch("app.main.index_status", return_value=report):
            response = self.client.get("/api/documents/status?offset=20&limit=20")
        payload = response.json()
        self.assertEqual(len(payload["documents"]), 20)
        self.assertEqual(payload["documents"][0]["file"], "0020.pdf")
        self.assertEqual(payload["documents_total"], 1000)
        self.assertNotIn("deleted.pdf", response.text)
        self.assertNotIn("missing_count", payload)
        self.assertEqual(self.client.get("/api/documents/status?limit=1000").status_code, 422)


if __name__ == "__main__":
    unittest.main()
