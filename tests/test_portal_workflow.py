import hashlib
import json
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app import portal_auth
from app.database import Base, get_db
from app.main import app
from app.models import AccountSession, PortalUser, RequestRecord, RequestWorkflow
from app.workflow import record_analysis


class PortalWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        folder = Path(self.temp.name)
        self.engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        self.factory = sessionmaker(bind=self.engine, expire_on_commit=False)
        def database():
            with self.factory() as db:
                yield db
        app.dependency_overrides[get_db] = database
        self.patches = [patch.object(portal_auth, "AUTH_PATH", folder / "admin-auth.json"),
                        patch.object(portal_auth, "ACCESS_PATH", folder / "admin-access.txt"),
                        patch.object(portal_auth, "ACCOUNTS_PATH", folder / "portal-accounts.txt"),
                        patch.object(portal_auth, "SessionLocal", self.factory),
                        patch.object(portal_auth, "_attempts", {})]
        for p in self.patches:
            p.start()
        self.clients = {}
        self.users = {}
        with self.factory() as db:
            for name, role in (("owner", "EMPLOYEE"), ("other", "EMPLOYEE"), ("analyst", "NEEDS_ANALYST"),
                               ("technical", "TECHNICAL_DESIGN"), ("engineering", "ENGINEERING_DESIGN")):
                self.users[name] = portal_auth.create_user(db, name, name + "-test-password", role, name)
            db.commit()
        for name in self.users:
            client = TestClient(app)
            self.assertEqual(client.post('/api/auth/login', json={"username": name, "password": "1234"}).status_code, 200)
            self.clients[name] = client
        self.owner, self.other, self.admin = [self.clients[n] for n in ("owner", "other", "analyst")]

    def tearDown(self):
        app.dependency_overrides.clear()
        for p in reversed(self.patches):
            p.stop()
        for client in self.clients.values():
            client.close()
        self.engine.dispose()
        self.temp.cleanup()

    def create_request(self, client=None):
        async def analysis(db, text, owner_hash):
            record = RequestRecord(text=text, category="Veri Analizi ve Raporlama", topic="Excel", coverage="VAR")
            db.add(record)
            db.flush()
            result = {"request_id": record.id, "ai_mode": "private-provider", "classification": {"category": record.category, "subcategory": "Excel", "risk_level": "NORMAL", "topic": "Excel"},
                      "coverage": {"status": "VAR", "fit_percent": 91, "retrieval_score": .8},
                      "courses": [{"course_id": 999, "course_name": "Excel dersi", "fit": {"percent": 91}, "evidence": [{"page_number": 3, "content": "PRIVATE RAW EXCERPT"}]}]}
            record_analysis(db, record, result, owner_hash)
            db.commit()
            return result
        import asyncio
        from app.workflow import request_detail
        account_name = next(name for name, candidate in self.clients.items() if candidate is (client or self.owner))
        with self.factory() as db:
            result = asyncio.run(analysis(db, "Sentetik Excel pivot eğitim ihtiyacı", f"user:{self.users[account_name].id}"))
            return request_detail(db, db.get(RequestRecord, result["request_id"]), db.get(RequestWorkflow, result["request_id"]))

    def refer(self, identifier, department="TECHNICAL_DESIGN", version=1, client=None, confirmed=True):
        return (client or self.admin).post(f"/api/admin/requests/{identifier}/refer", json={
            "department": department, "training_need_confirmed": confirmed,
            "analysis_summary": "Sentetik ihtiyaç analizi tamamlandı. Uygulamalı eğitim tasarımı gerekiyor.",
            "expected_version": version})

    def test_every_data_endpoint_requires_login_and_legacy_admin_cookie_is_not_auth(self):
        guest = TestClient(app)
        guest.cookies.set("learning_portal_session", "old-cookie")
        self.assertFalse(guest.get('/api/portal/session').json()["authenticated"])
        for endpoint in ('/api/requests/mine', '/api/admin/requests', '/api/documents/status', '/api/health', '/api/taxonomy', '/api/portal/health'):
            self.assertEqual(guest.get(endpoint).status_code, 401, endpoint)
        self.assertEqual(guest.post('/api/requests/analyze', json={"text": "Sentetik talep"}).status_code, 401)
        self.assertEqual(guest.post('/api/admin/login', json={"password": "1234"}).status_code, 422)
        self.assertEqual(guest.get('/openapi.json').status_code, 404)

    def test_employee_response_has_no_raw_pdf_model_or_internal_score(self):
        result = self.create_request()
        for forbidden in ("evidence", "page_number", "PRIVATE", "retrieval_score", "ai_mode"):
            self.assertNotIn(forbidden, json.dumps(result))
        self.assertEqual(result["coverage"]["fit_percent"], 91)
        detail = self.owner.get('/api/requests/' + str(result["request_id"]))
        self.assertNotIn("PRIVATE", detail.text)
        self.assertNotIn("page_number", detail.text)

    def test_other_account_cannot_list_read_change_or_chat_against_my_request(self):
        identifier = self.create_request()["request_id"]
        self.assertEqual(self.other.get('/api/requests/mine').json()["total"], 0)
        self.assertEqual(self.other.get(f'/api/requests/{identifier}').status_code, 404)
        self.assertEqual(self.other.patch(f'/api/requests/{identifier}/status', json={"status": "RESOLVED", "note": "Changed", "expected_version": 1}).status_code, 404)
        self.assertEqual(self.other.post('/api/chat', json={"request_id": identifier, "question": "Private context?"}).status_code, 404)

    def test_same_employee_account_retains_history_across_browsers(self):
        identifier = self.create_request()["request_id"]
        second = TestClient(app)
        second.post('/api/auth/login', json={"username": "owner", "password": "1234"}).raise_for_status()
        self.assertEqual(second.get('/api/requests/mine').json()["items"][0]["request_id"], identifier)
        self.assertEqual(second.get(f'/api/requests/{identifier}').status_code, 200)

    def test_logout_expiry_deactivation_and_session_rotation_are_enforced(self):
        old_token = self.owner.cookies.get(portal_auth.COOKIE)
        self.owner.post('/api/auth/login', json={"username": "owner", "password": "1234"}).raise_for_status()
        self.assertNotEqual(old_token, self.owner.cookies.get(portal_auth.COOKIE))
        replay = TestClient(app)
        replay.cookies.set(portal_auth.COOKIE, old_token)
        self.assertEqual(replay.get('/api/requests/mine').status_code, 401)
        self.owner.post('/api/auth/logout').raise_for_status()
        self.assertEqual(self.owner.get('/api/requests/mine').status_code, 401)
        with self.factory() as db:
            user = db.get(PortalUser, self.users["other"].id)
            user.active = False
            for session in db.scalars(select(AccountSession).where(AccountSession.user_id == self.users["analyst"].id)):
                session.expires_at = datetime.utcnow() - timedelta(seconds=1)
            db.commit()
        self.assertEqual(self.other.get('/api/requests/mine').status_code, 401)
        self.assertEqual(self.admin.get('/api/admin/requests').status_code, 401)

    def test_all_administrative_reads_and_writes_require_appropriate_role(self):
        for name in ("owner", "technical", "engineering"):
            client = self.clients[name]
            for endpoint in ('/api/documents/status', '/api/health', '/api/courses', '/api/dashboard'):
                self.assertEqual(client.get(endpoint).status_code, 403, (name, endpoint))
            self.assertEqual(client.post('/api/documents/sync').status_code, 403)
            self.assertEqual(client.post('/api/reviews', json={"request_id": 1, "approved": True}).status_code, 403)
        self.assertEqual(self.owner.get('/api/admin/requests').status_code, 403)
        for name in ("analyst", "technical", "engineering"):
            self.assertEqual(self.clients[name].post('/api/requests/analyze', json={"text": "Manager forged employee"}).status_code, 403)

    def test_legacy_records_are_analyst_only_until_explicit_referral(self):
        with self.factory() as db:
            record = RequestRecord(text="Legacy synthetic record", category="Old")
            db.add(record)
            db.commit()
            identifier = record.id
        listed = self.admin.get('/api/admin/requests').json()
        self.assertEqual(listed["items"][0]["status"], "LEGACY")
        self.assertIsNone(listed["items"][0]["fit_percent"])
        self.assertEqual(self.owner.get('/api/requests/mine').json()["total"], 0)
        self.assertEqual(self.clients["technical"].get('/api/admin/requests').json()["total"], 0)
        self.assertEqual(self.refer(identifier, version=0).status_code, 200)
        self.assertEqual(self.clients["technical"].get(f'/api/admin/requests/{identifier}').status_code, 200)

    def test_designers_only_see_completed_analysis_referred_to_their_department(self):
        identifier = self.create_request()["request_id"]
        for name in ("technical", "engineering"):
            client = self.clients[name]
            self.assertEqual(client.get('/api/admin/requests').json()["summary"]["total"], 0)
            self.assertEqual(client.get(f'/api/admin/requests/{identifier}').status_code, 404)
            self.assertEqual(client.patch(f'/api/admin/requests/{identifier}/status', json={"status": "ACTION_PLANNED", "note": "Premature", "expected_version": 1}).status_code, 404)
        self.assertEqual(self.refer(identifier, confirmed=False).status_code, 422)
        self.assertEqual(self.refer(identifier, client=self.clients["technical"]).status_code, 403)
        response = self.refer(identifier)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["status"], "REFERRED")
        self.assertEqual(response.json()["version"], 2)
        self.assertTrue(response.json()["referral"]["training_need_confirmed"])
        tech = self.clients["technical"]
        self.assertEqual(tech.get('/api/admin/requests?status=REFERRED').json()["total"], 1)
        detail = tech.get(f'/api/admin/requests/{identifier}')
        self.assertEqual(detail.status_code, 200)
        self.assertNotIn("PRIVATE", detail.text)
        self.assertFalse(detail.json()["permissions"]["can_refer"])
        self.assertEqual(self.clients["engineering"].get(f'/api/admin/requests/{identifier}').status_code, 404)
        self.assertEqual(self.clients["engineering"].get('/api/admin/requests').json()["total"], 0)
        self.assertEqual(tech.patch(f'/api/admin/requests/{identifier}/status', json={"status": "ACTION_PLANNED", "note": "Tasarım planı hazırlanıyor", "expected_version": 2}).status_code, 200)
        self.assertEqual(self.owner.get(f'/api/requests/{identifier}').json()["status"], "ACTION_PLANNED")

    def test_reassignment_revokes_old_department_and_stale_updates_cannot_overwrite(self):
        identifier = self.create_request()["request_id"]
        self.assertEqual(self.refer(identifier).status_code, 200)
        self.assertEqual(self.refer(identifier, "ENGINEERING_DESIGN", version=1).status_code, 409)
        response = self.refer(identifier, "ENGINEERING_DESIGN", version=2)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()["events"]), 3)
        self.assertEqual(self.clients["technical"].get(f'/api/admin/requests/{identifier}').status_code, 404)
        self.assertEqual(self.clients["engineering"].get(f'/api/admin/requests/{identifier}').status_code, 200)

    def test_return_to_analysis_hides_from_designers_until_new_referral(self):
        identifier = self.create_request()["request_id"]
        self.refer(identifier).raise_for_status()
        tech = self.clients["technical"]
        response = tech.patch(f'/api/admin/requests/{identifier}/status', json={"status": "IN_REVIEW", "note": "Kapsam için ek analiz gerekiyor", "expected_version": 2})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["referral"]["active"])
        self.assertEqual(tech.get('/api/admin/requests').json()["total"], 0)
        self.assertEqual(tech.get(f'/api/admin/requests/{identifier}').status_code, 404)
        self.assertEqual(self.refer(identifier, version=3).status_code, 200)

    def test_match_is_not_resolution_and_resolution_is_audited_and_reopenable(self):
        identifier = self.create_request()["request_id"]
        summary = self.owner.get('/api/requests/mine').json()["summary"]
        self.assertEqual(summary["IN_REVIEW"], 1)
        self.assertEqual(summary["RESOLVED"], 0)
        resolved = self.owner.patch(f'/api/requests/{identifier}/status', json={"status": "RESOLVED", "note": "Sentetik eğitim ihtiyacımı karşıladı", "expected_version": 1})
        self.assertEqual(resolved.status_code, 422)
        self.refer(identifier).raise_for_status()
        self.clients["technical"].post(f'/api/admin/requests/{identifier}/actions', json={
            "action": "SAVE_PLAN", "summary": "Sentetik eğitim ve uygulama planı", "responsible_unit": "TECHNICAL_DESIGN",
            "expected_version": 2}).raise_for_status()
        resolved = self.owner.patch(f'/api/requests/{identifier}/status', json={"status": "RESOLVED", "note": "Eğitim uygulandı ve ihtiyaç karşılandı", "expected_version": 3})
        self.assertEqual(resolved.status_code, 200)
        self.assertEqual(len(resolved.json()["events"]), 5)
        self.assertEqual(self.owner.get('/api/requests/mine?status=RESOLVED').json()["total"], 1)
        self.assertEqual(self.refer(identifier, version=2).status_code, 409)
        stale = self.owner.patch(f'/api/requests/{identifier}/status', json={"status": "IN_REVIEW", "note": "Reopen", "expected_version": 1})
        self.assertEqual(stale.status_code, 409)
        reopened = self.owner.patch(f'/api/requests/{identifier}/status', json={"status": "IN_REVIEW", "note": "Ek ihtiyaç oluştu", "expected_version": 4})
        self.assertEqual(reopened.status_code, 200)
        self.assertEqual(self.owner.get('/api/requests/mine?status=RESOLVED').json()["total"], 0)

    def test_status_filters_search_and_pagination_have_real_distinct_results(self):
        first, second = self.create_request()["request_id"], self.create_request()["request_id"]
        self.admin.patch(f'/api/admin/requests/{first}/status', json={"status": "NEEDS_INFO", "note": "Ek kapsam bilgisi gerekiyor", "expected_version": 1}).raise_for_status()
        self.refer(second, "ENGINEERING_DESIGN").raise_for_status()
        for status, expected in (("NEEDS_INFO", 1), ("REFERRED", 1), ("RESOLVED", 0), ("IN_REVIEW", 0)):
            data = self.admin.get('/api/admin/requests', params={"status": status}).json()
            self.assertEqual(data["total"], expected)
            self.assertTrue(all(item["status"] == status for item in data["items"]))
        self.assertEqual(self.admin.get('/api/admin/requests?status=invalid').status_code, 422)
        self.assertEqual(self.admin.get('/api/admin/requests?search=not-found').json()["total"], 0)
        self.assertEqual(self.admin.get('/api/admin/requests?search=%25').json()["total"], 0)
        page = self.admin.get('/api/admin/requests?limit=1&offset=1').json()
        self.assertEqual(page["items"][0]["request_id"], first)
        self.assertEqual(page["total"], 2)
        update = self.owner.patch(f'/api/requests/{first}/status', json={"status": "IN_REVIEW", "note": "İstenen ek bilgiyi iletiyorum", "expected_version": 2})
        self.assertEqual(update.status_code, 200)

    def test_employee_cannot_set_manager_states(self):
        identifier = self.create_request()["request_id"]
        self.assertEqual(self.owner.patch(f'/api/requests/{identifier}/status', json={"status": "ACTION_PLANNED", "note": "Unauthorized", "expected_version": 1}).status_code, 422)

    def test_cross_origin_changes_and_brute_force_are_rejected(self):
        guest = TestClient(app)
        payload = {"username": "owner", "password": "1234"}
        self.assertEqual(guest.post('/api/auth/login', json=payload, headers={"Origin": "https://untrusted.example"}).status_code, 403)
        for _ in range(5):
            self.assertEqual(guest.post('/api/auth/login', json={**payload, "password": "incorrect"}).status_code, 401)
        self.assertEqual(guest.post('/api/auth/login', json=payload).status_code, 429)

    def test_employee_preparation_and_health_do_not_reveal_inventory(self):
        state = {"ai_status": "connected", "detail": "PRIVATE MODEL DETAILS"}
        with patch('app.main.ai_client.healthcheck', new=AsyncMock(return_value=state)):
            self.assertNotIn("PRIVATE", self.owner.get('/api/portal/health').text)
        report = {"complete": True, "error_count": 0, "documents": [{"file": "PRIVATE.pdf", "status": "ready"}]}
        with patch('app.main.index_status', return_value=report):
            response = self.owner.get('/api/portal/preparation')
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("PRIVATE", response.text)
        self.assertTrue(response.json()["ready"])

    def test_all_existing_and_future_accounts_use_fixed_password(self):
        with self.factory() as db:
            custom = portal_auth.create_user(db, "future", "ignored-password", "EMPLOYEE", "Future")
            db.commit()
            self.assertEqual(custom.password_hash, portal_auth.password_digest("1234", custom.password_salt))
            owner = db.scalar(select(PortalUser).where(PortalUser.username == "owner"))
            owner.password_hash = portal_auth.password_digest("old-password", owner.password_salt)
            db.commit()
        portal_auth.ensure_admin_credentials()
        with self.factory() as db:
            for user in db.scalars(select(PortalUser)):
                self.assertEqual(user.password_hash, portal_auth.password_digest("1234", user.password_salt))
        guest = TestClient(app)
        self.assertEqual(guest.post('/api/auth/login', json={"username": "future", "password": "1234"}).status_code, 200)
        self.assertEqual(guest.post('/api/auth/login', json={"username": "future", "password": "ignored-password"}).status_code, 401)
