import asyncio
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import fitz
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from app import indexing, services
from app.ai import AIResponseError
from app.database import Base
from app.models import Course, CourseChunk, DocumentIndex, HumanReview, LearnedMapping, RequestMatch, RequestRecord, RequestWorkflow


class DirectoryIndexTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="tusas-index-test-")
        self.root = Path(self.temp.name).resolve()
        self.pdfs = self.root / "pdfs"
        self.pdfs.mkdir()
        self.engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine, expire_on_commit=False)()
        async def embed(texts, *, is_query=False):
            return [[1.0, 0.25, 0.5] for _ in texts]
        async def rerank(query, documents, top_n):
            return [{"index": i, "relevance_score": 0.9} for i in range(min(top_n, len(documents)))]
        self.ai = SimpleNamespace(provider_name="test-embedding", embed=AsyncMock(side_effect=embed),
                                  rerank=AsyncMock(side_effect=rerank))
        self.config = SimpleNamespace(pdf_dir=self.pdfs, top_k_retrieve=16, top_k_rerank=6)
        lock = asyncio.Lock()
        self.patches = [patch.object(indexing, "settings", self.config),
                        patch.object(services, "settings", self.config),
                        patch.object(indexing, "ai_client", self.ai),
                        patch.object(services, "ai_client", self.ai),
                        patch.object(indexing, "sync_lock", lock),
                        patch.object(services, "sync_lock", lock)]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()
        self.db.close()
        self.engine.dispose()
        self.temp.cleanup()

    def pdf(self, name, text="Synthetic Excel pivot training", pages=1):
        path = self.pdfs / name
        path.parent.mkdir(parents=True, exist_ok=True)
        with fitz.open() as doc:
            for _ in range(pages):
                doc.new_page().insert_text((50, 50), text)
            doc.save(path)
        return path

    def courses(self):
        return self.db.scalars(select(Course)).all()

    async def test_new_files_nested_and_uppercase_extension_are_discovered(self):
        self.pdf("excel.pdf")
        self.pdf("nested/python.PDF", "Synthetic Python automation")
        report = await indexing.sync_pdf_directory(self.db)
        self.assertTrue(report["complete"])
        self.assertEqual(report["ready_count"], 2)
        self.assertEqual(len(indexing.active_course_ids(self.db)), 2)
        self.assertEqual({c.name for c in self.courses()}, {"excel", "python"})

    async def test_unchanged_files_do_not_call_embedding_again(self):
        self.pdf("excel.pdf")
        await indexing.sync_pdf_directory(self.db)
        count = self.ai.embed.await_count
        await indexing.sync_pdf_directory(self.db)
        self.assertEqual(self.ai.embed.await_count, count)

    async def test_deleted_file_is_removed_from_retrieval_not_history(self):
        deleted = self.pdf("ABC.pdf")
        self.pdf("new.pdf", "Synthetic new course")
        await indexing.sync_pdf_directory(self.db)
        old_course = next(c for c in self.courses() if c.name == "ABC")
        self.db.add(LearnedMapping(canonical_intent="excel", course_id=old_course.id, weight=0.3))
        historical = RequestRecord(text="Historical request")
        self.db.add(historical)
        self.db.flush()
        self.db.add(RequestMatch(request_id=historical.id, course_id=old_course.id, score=0.9, evidence_json='[{"content":"Historical evidence"}]'))
        self.db.add(HumanReview(request_id=historical.id, approved=True, correct_course_id=old_course.id, comment="Historical review"))
        self.db.commit()
        deleted.unlink()
        results = await services.retrieve(self.db, "Excel", "excel")
        self.assertTrue(results)
        self.assertNotIn(old_course.id, [r["chunk"].course_id for r in results])
        self.assertEqual(indexing.index_status(self.db)["missing_count"], 1)
        self.assertIsNotNone(self.db.get(Course, old_course.id))
        self.assertEqual(self.db.scalar(select(func.count(RequestRecord.id))), 1)
        self.assertEqual(self.db.scalar(select(func.count(CourseChunk.id)).where(CourseChunk.course_id == old_course.id)), 0)
        self.assertEqual(self.db.scalar(select(func.count(DocumentIndex.path_key)).where(DocumentIndex.course_id == old_course.id)), 0)
        self.assertEqual(self.db.scalar(select(func.count(LearnedMapping.id)).where(LearnedMapping.course_id == old_course.id)), 0)
        self.assertNotIn("ABC.pdf", str(indexing.public_status(indexing.index_status(self.db))))
        self.assertIn("Historical evidence", self.db.scalar(select(RequestMatch.evidence_json)))
        self.assertEqual(self.db.scalar(select(HumanReview.comment)), "Historical review")

    async def analyze_saved(self, text, owner_hash="user:123"):
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

    async def test_full_analysis_success_keeps_real_pdf_evidence_and_persists_once(self):
        self.pdf("excel.pdf", "Synthetic Excel pivot training")
        self.config.ai_mode = "test"
        self.ai.classify_request = AsyncMock(return_value={"category": "Data", "topic": "Excel", "intent": "Training", "canonical_intent": "excel", "search_query": "Excel pivot"})
        async def coverage(text, classification, evidence):
            return {"coverage": "VAR", "evidence_strength": "GUCLU", "reason": "Synthetic test match", "course_assessments": [{"course_code": evidence[0]["course_code"], "summary": "Synthetic match", "topics": ["Excel"], "needs": [["N1", "FULL", ["E1"]]], "evidence_support": [{"need_id": "N1", "evidence_id": "E1", "quote": "Synthetic Excel pivot training"}]}]}
        self.ai.coverage_analysis = AsyncMock(side_effect=coverage)
        result = await self.analyze_saved("Synthetic training need")
        self.assertEqual(result["coverage"]["status"], "VAR")
        self.assertEqual(result["courses"][0]["course_name"], "excel")
        self.assertIn("Synthetic Excel pivot", result["courses"][0]["evidence"][0]["content"])
        self.assertEqual(self.db.scalar(select(func.count(RequestRecord.id))), 1)
        self.assertEqual(self.db.scalar(select(func.count(RequestMatch.id))), 1)

    async def test_deleted_source_disappears_before_sync_and_can_be_readded(self):
        path = self.pdf("ABC.pdf")
        await indexing.sync_pdf_directory(self.db)
        original = self.courses()[0].id
        path.unlink()
        self.assertEqual(indexing.public_status(indexing.index_status(self.db))["documents"], [])
        await indexing.sync_pdf_directory(self.db)
        self.pdf("ABC.pdf", "New readded content")
        report = await indexing.sync_pdf_directory(self.db)
        self.assertEqual(report["ready_count"], 1)
        self.assertEqual(self.courses()[0].id, original)
        self.assertIn("New readded content", self.db.scalar(select(CourseChunk.content)))

    async def test_no_matching_training_is_a_saved_unmet_need_not_an_ai_failure(self):
        self.pdf("excel.pdf", "Synthetic unrelated spreadsheet lesson")
        self.config.ai_mode = "test"
        self.ai.classify_request = AsyncMock(return_value={"category": "Science", "topic": "Impulse", "intent": "Training", "requirements": [{"id": "N1", "label": "Impulse"}]})
        self.ai.coverage_analysis = AsyncMock(return_value={"coverage": "YOK", "course_assessments": [], "matched_course_codes": []})
        result = await self.analyze_saved("Synthetic physics need")
        self.assertEqual(result["coverage"]["status"], "YOK")
        self.assertEqual(result["coverage"]["fit_percent"], 0)
        self.assertEqual(result["coverage"]["missing_topics"], ["Impulse"])
        self.assertEqual(result["courses"], [])
        self.assertEqual(self.db.scalar(select(func.count(RequestRecord.id))), 1)
        flow = self.db.get(RequestWorkflow, result["request_id"])
        self.assertEqual(flow.owner_hash, "user:123")
        self.assertEqual(flow.status, "IN_REVIEW")

    async def test_positive_match_without_valid_course_assessment_still_fails_closed(self):
        self.pdf("excel.pdf")
        self.config.ai_mode = "test"
        self.ai.classify_request = AsyncMock(return_value={"topic": "Excel", "intent": "Training"})
        for decision in ("VAR", "KISMEN_VAR"):
            for assessments in ([], [{"course_code": "INVENTED"}]):
                self.ai.coverage_analysis = AsyncMock(return_value={"coverage": decision, "course_assessments": assessments})
                with self.assertRaises(AIResponseError):
                    await services.compute_analysis(self.db, "Synthetic need")
                self.assertEqual(self.db.scalar(select(func.count(RequestRecord.id))), 0)

    async def test_legacy_missing_abc_is_never_retrieved(self):
        old = Course(code="ABC", name="Old", pdf_path=str(self.pdfs / "deleted.pdf"))
        self.db.add(old)
        self.db.flush()
        self.db.add(CourseChunk(course_id=old.id, page_number=1, chunk_index=0, content="stale",
                                embedding_json="[1, 0.25, 0.5]", embedding_provider=self.ai.provider_name))
        self.db.commit()
        self.assertEqual(await services.retrieve(self.db, "Excel", ""), [])
        self.ai.embed.assert_not_awaited()

    async def test_legacy_existing_pdf_is_adopted_without_duplicate_course(self):
        path = self.pdf("ABC.pdf")
        self.db.add(Course(code="ABC", name="Custom title", pdf_path=str(path)))
        self.db.commit()
        await indexing.sync_pdf_directory(self.db)
        self.assertEqual(len(self.courses()), 1)
        self.assertEqual(self.courses()[0].name, "Custom title")
        self.assertEqual(indexing.index_status(self.db)["ready_count"], 1)

    async def test_changed_content_reindexes_even_with_preserved_mtime(self):
        path = self.pdf("same.pdf", "Old content")
        await indexing.sync_pdf_directory(self.db)
        timestamp = path.stat().st_mtime
        self.pdf("same.pdf", "New content")
        os.utime(path, (timestamp, timestamp))
        self.assertEqual(indexing.index_status(self.db)["pending_count"], 1)
        await indexing.sync_pdf_directory(self.db)
        contents = self.db.scalars(select(CourseChunk.content)).all()
        self.assertTrue(any("New content" in c for c in contents))
        self.assertFalse(any("Old content" in c for c in contents))
        self.assertEqual(len(self.courses()), 1)

    async def test_provider_change_reindexes(self):
        self.pdf("course.pdf")
        await indexing.sync_pdf_directory(self.db)
        self.ai.provider_name = "new-model"
        report = await indexing.sync_pdf_directory(self.db)
        self.assertEqual(report["ready_count"], 1)
        self.assertEqual(self.db.scalar(select(CourseChunk.embedding_provider)), "new-model")

    async def test_chunk_config_change_invalidates_then_rebuilds_existing_index(self):
        self.pdf("course.pdf")
        await indexing.sync_pdf_directory(self.db)
        initial_calls = self.ai.embed.await_count
        initial_pipeline = self.db.scalar(select(DocumentIndex.pipeline_version))
        self.config.chunk_size, self.config.chunk_overlap = 1000, 150
        self.assertEqual(indexing.index_status(self.db)["pending_count"], 1)
        self.assertEqual(indexing.active_course_ids(self.db), set())
        report = await indexing.sync_pdf_directory(self.db)
        self.assertTrue(report["complete"])
        self.assertGreater(self.ai.embed.await_count, initial_calls)
        self.assertNotEqual(initial_pipeline, self.db.scalar(select(DocumentIndex.pipeline_version)))
        self.assertEqual(len(self.courses()), 1)

    async def test_failed_replacement_keeps_old_chunks_but_excludes_them(self):
        self.pdf("course.pdf", "Old content")
        await indexing.sync_pdf_directory(self.db)
        self.pdf("course.pdf", "New content")
        self.ai.embed.side_effect = AIResponseError("Test failure")
        report = await indexing.sync_pdf_directory(self.db)
        self.assertEqual(report["error_count"], 1)
        self.assertFalse(report["complete"])
        self.assertEqual(indexing.active_course_ids(self.db), set())
        self.assertIn("Old content", self.db.scalar(select(CourseChunk.content)))
        with self.assertRaises(indexing.IndexNotReadyError):
            await services.retrieve(self.db, "query", "")

    async def test_empty_pdf_reports_ocr_requirement(self):
        self.pdf("scan.pdf", "")
        report = await indexing.sync_pdf_directory(self.db)
        self.assertEqual(report["error_count"], 1)
        self.assertIn("OCR", report["documents"][0]["error"])
        self.ai.embed.assert_not_awaited()

    async def test_malformed_file_does_not_hide_healthy_file(self):
        self.pdf("valid.pdf")
        (self.pdfs / "broken.pdf").write_bytes(b"not a PDF")
        report = await indexing.sync_pdf_directory(self.db)
        self.assertEqual(report["ready_count"], 1)
        self.assertEqual(report["error_count"], 1)
        self.assertFalse(report["complete"])

    async def test_short_embedding_batch_cannot_be_marked_ready(self):
        self.pdf("two.pdf", pages=2)
        self.ai.embed.side_effect = None
        self.ai.embed.return_value = [[1.0]]
        report = await indexing.sync_pdf_directory(self.db)
        self.assertEqual(report["error_count"], 1)
        self.assertEqual(self.db.scalar(select(func.count(CourseChunk.id))), 0)

    async def test_file_deleted_during_reranking_cannot_be_returned(self):
        path = self.pdf("course.pdf")
        async def remove(query, documents, top_n):
            path.unlink()
            return [{"index": 0, "relevance_score": 1}]
        self.ai.rerank.side_effect = remove
        with self.assertRaises(indexing.IndexNotReadyError):
            await services.retrieve(self.db, "query", "")

    async def test_concurrent_sync_does_not_create_duplicate_courses(self):
        self.pdf("course.pdf")
        await asyncio.gather(indexing.sync_pdf_directory(self.db), indexing.sync_pdf_directory(self.db))
        self.assertEqual(len(self.courses()), 1)
        self.assertEqual(self.ai.embed.await_count, 1)

    async def test_missing_root_is_an_error_not_an_empty_success(self):
        self.pdfs.rmdir()
        with self.assertRaises(OSError):
            await indexing.sync_pdf_directory(self.db)

    async def test_upload_rejects_path_escape_and_does_not_overwrite(self):
        path = self.pdf("source.pdf")
        with self.assertRaises(ValueError):
            await services.ingest_pdf(self.db, course_code="../ABC", course_name="name", description="", source_path=path)
        protected = self.pdf("ABC.pdf", "Keep this content")
        digest = indexing.fingerprint(protected)
        with self.assertRaises(ValueError):
            await services.ingest_pdf(self.db, course_code="ABC", course_name="name", description="", source_path=path)
        self.assertEqual(indexing.fingerprint(protected), digest)

    async def test_api_upload_joins_the_same_index_without_duplicates(self):
        source = self.root / "upload.pdf"
        with fitz.open() as doc:
            doc.new_page().insert_text((50, 50), "Synthetic uploaded content")
            doc.save(source)
        course = await services.ingest_pdf(self.db, course_code="UP1", course_name="Uploaded", description="", source_path=source)
        await indexing.sync_pdf_directory(self.db)
        self.assertEqual(len(self.courses()), 1)
        self.assertIn(course.id, indexing.active_course_ids(self.db))


if __name__ == "__main__":
    unittest.main()
