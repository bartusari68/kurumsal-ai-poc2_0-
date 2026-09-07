from pathlib import Path
p=Path('tests/test_portal_workflow.py');s=p.read_text(encoding='utf-8')
a=s.index('        with patch("app.main.analyze_request",');b=s.index('\n    def refer(',a)
s=s[:a]+'''        import asyncio
        from app.workflow import request_detail
        account_name = next(name for name, candidate in self.clients.items() if candidate is (client or self.owner))
        with self.factory() as db:
            result = asyncio.run(analysis(db, "Sentetik Excel pivot eğitim ihtiyacı", f"user:{self.users[account_name].id}"))
            return request_detail(db, db.get(RequestRecord, result["request_id"]), db.get(RequestWorkflow, result["request_id"]))
''' +s[b:]
p.write_text(s,encoding='utf-8')

p=Path('tests/test_indexing.py');s=p.read_text(encoding='utf-8')
s=s.replace('    async def test_full_analysis_success_keeps_real_pdf_evidence_and_persists_once(self):', '''    async def analyze_saved(self, text, owner_hash="user:123"):
        from app.analysis_pipeline import persist_request, execute_run, latest_run, current_result
        from app.models import PortalUser
        from app.portal_auth import Principal
        user = self.db.get(PortalUser, 123)
        if not user:
            user = PortalUser(id=123, username="synthetic", display_name="Synthetic", role="EMPLOYEE", password_salt="0"*32, password_hash="0"*64)
            self.db.add(user)
            self.db.commit()
        row, flow = persist_request(self.db, text, Principal(user.id, user.username, user.display_name, user.role), None)
        run = latest_run(self.db, row.id)
        self.assertTrue(await execute_run(sessionmaker(bind=self.engine, expire_on_commit=False), run.id, services.compute_analysis))
        self.db.expire_all()
        return current_result(self.db, row, flow)

    async def test_full_analysis_success_keeps_real_pdf_evidence_and_persists_once(self):''')
s=s.replace('await services.analyze_request(self.db, "Synthetic training need")', 'await self.analyze_saved("Synthetic training need")')
s=s.replace('await services.analyze_request(self.db, "Synthetic physics need", owner_hash="user:123")', 'await self.analyze_saved("Synthetic physics need")')
s=s.replace('await services.analyze_request(self.db, "Synthetic need")', 'await services.compute_analysis(self.db, "Synthetic need")')
p.write_text(s,encoding='utf-8')

p=Path('tests/test_api.py');s=p.read_text(encoding='utf-8')
s=s.replace('        cls.client = TestClient(app)', '''        from sqlalchemy import create_engine
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
        cls.client = TestClient(app)''')
s=s.replace('        app.dependency_overrides.clear()','        app.dependency_overrides.clear()\n        cls.client.close()\n        cls.engine.dispose()',1)
a=s.index('    def test_analyze_quota_');b=s.index('    def test_ai_client_does_not',a)
s=s[:a]+'''    def analyzed(self, *, error=None, result=None):
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

'''+s[b:]
a=s.index('    def test_incomplete_index_returns');b=s.index('    def test_folder_sync',a)
s=s[:a]+'''    def test_incomplete_index_is_a_failed_analysis_with_a_retained_request(self):
        response = self.analyzed(error=IndexNotReadyError({"complete": False, "error_count": 1, "documents": []}))
        self.assertEqual(response.json()["analysis_state"]["latest_run"]["error_code"], "SOURCE_UNAVAILABLE")
        self.assertNotIn("document_index", response.json())

'''+s[b:]
p.write_text(s,encoding='utf-8')

p=Path('tests/frontend.test.cjs');s=p.read_text(encoding='utf-8')
s=s.replace("assert.equal(nodes['#submitterAnalyzeButton'].disabled,true);", "assert.equal(nodes['#submitterAnalyzeButton'].disabled,false);")
p.write_text(s,encoding='utf-8')
