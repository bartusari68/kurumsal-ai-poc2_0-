"""Integration boundaries and grounded policy use synthetic data only."""
import copy
import unittest
from unittest.mock import AsyncMock, patch

from app.ai import AIClient, AIResponseError, validate_coverage_result, validate_rerank_results, validate_vectors
from app.scoring import course_fit, coverage_policy
from tests.test_indexing import DirectoryIndexTests


class GroundingTests(unittest.TestCase):
    def setUp(self):
        self.needs = [{"id": "N1", "label": "Pivot tablosu"}, {"id": "N2", "label": "Veri birleştirme"}]
        self.evidence = [{"evidence_id": "E1", "course_code": "EXCEL", "content": "Pivot tablosu oluşturma ve veri birleştirme uygulaması.", "rerank_score": 1, "semantic_score": 1}]
        self.result = {"coverage": "VAR", "evidence_strength": "GUCLU", "matched_course_codes": ["EXCEL"],
                       "course_assessments": [{"course_code": "EXCEL", "summary": "Özet", "topics": ["Pivot"],
                                               "needs": [["N1", "FULL", ["E1"]], ["N2", "FULL", ["E1"]]],
                                               "evidence_support": [{"need_id": "N1", "evidence_id": "E1", "quote": "Pivot tablosu oluşturma"},
                                                                    {"need_id": "N2", "evidence_id": "E1", "quote": "veri birleştirme uygulaması"}]}]}

    def validate(self, result=None):
        return validate_coverage_result(self.result if result is None else result, self.needs, self.evidence)

    def test_verified_positive_preserves_internal_provenance_and_computes_full_fit(self):
        result = self.validate()
        fit = course_fit(self.needs, result["course_assessments"][0], self.evidence)
        self.assertEqual(fit["percent"], 100)
        self.assertTrue(fit["grounding_verified"])
        self.assertEqual(coverage_policy(fit, self.needs, evidence_strength="GUCLU")["status"], "VAR")

    def test_hallucinated_course_need_or_quote_is_an_error_not_no_course(self):
        invalid = []
        for field, value in (("course_code", "INVENTED"), ("needs", [["N9", "FULL", ["E1"]]]),
                             ("evidence_support", [{"need_id": "N1", "evidence_id": "E1", "quote": "This quote does not exist"}])):
            result = copy.deepcopy(self.result)
            result["course_assessments"][0][field] = value
            invalid.append(result)
        result = copy.deepcopy(self.result)
        result["matched_course_codes"] = ["INVENTED"]
        invalid.append(result)
        for result in invalid:
            with self.subTest(result=result), self.assertRaises(AIResponseError):
                self.validate(result)

    def test_foreign_evidence_duplicate_or_unassessed_need_fails_closed(self):
        self.evidence.append({"evidence_id": "E2", "course_code": "PYTHON", "content": "Pivot tablosu oluşturma"})
        for case in ("foreign", "duplicate", "omitted", "unquoted"):
            result = copy.deepcopy(self.result)
            assessment = result["course_assessments"][0]
            if case == "foreign":
                assessment["needs"][0][2] = ["E2"]
                assessment["evidence_support"][0]["evidence_id"] = "E2"
            elif case == "duplicate":
                assessment["needs"].append(assessment["needs"][0])
            elif case == "omitted":
                assessment["needs"].pop()
            else:
                assessment["evidence_support"] = []
            with self.subTest(case=case), self.assertRaises(AIResponseError):
                self.validate(result)

    def test_supported_no_match_and_empty_catalog_remain_valid(self):
        result = {"coverage": "YOK", "course_assessments": [], "matched_course_codes": []}
        self.assertEqual(self.validate(result)["coverage"], "YOK")
        self.assertEqual(validate_coverage_result(result, self.needs, [])["course_assessments"], [])

    def test_no_model_text_can_bypass_server_thresholds(self):
        for percent, states, strength, expected in (
            (0, ["NONE", "NONE"], "DUSUK", "YOK"),
            (40, ["FULL", "NONE"], "GUCLU", "YOK"),
            (41, ["FULL", "NONE"], "GUCLU", "KISMEN_VAR"),
            (94, ["FULL", "FULL"], "GUCLU", "KISMEN_VAR"),
            (95, ["FULL", "FULL"], "GUCLU", "VAR"),
            (100, ["FULL", "PARTIAL"], "GUCLU", "KISMEN_VAR"),
            (100, ["FULL", "FULL"], "DUSUK", "KISMEN_VAR"),
        ):
            fit = {"percent": percent, "grounding_verified": True, "requirements": [dict(need, status=state) for need, state in zip(self.needs, states)]}
            policy = coverage_policy(fit, self.needs, evidence_strength=strength)
            with self.subTest(percent=percent, states=states, strength=strength):
                self.assertEqual(policy["status"], expected)
                self.assertEqual(policy["needs_new_course"], expected == "YOK")
        policy = coverage_policy(None, self.needs, need_type="SUREC_ARAC")
        self.assertFalse(policy["needs_new_course"])
        self.assertEqual(policy["next_action"], "EGITIM_DISI_COZUM")
        policy = coverage_policy(None, self.needs, need_type="PERFORMANS_DESTEGI")
        self.assertFalse(policy["needs_new_course"])
        policy = coverage_policy(None, self.needs, risk_level="KRITIK")
        self.assertFalse(policy["needs_new_course"])
        self.assertEqual(policy["next_action"], "ACIL_INCELEME")

    def test_one_of_four_needs_cannot_gain_relevance_points_from_unmet_needs(self):
        needs = [{"id": f"N{i}", "label": str(i)} for i in range(1, 5)]
        fit = course_fit(needs, {"needs": [["N1", "FULL", ["E1"]]]}, self.evidence)
        self.assertEqual(fit["percent"], 25)
        self.assertEqual(coverage_policy(fit, needs)["status"], "YOK")


class ProviderOutputValidationTests(unittest.IsolatedAsyncioTestCase):
    async def test_truncated_json_is_rejected_even_when_json_parses(self):
        ai = AIClient()
        ai.api_key = "synthetic"
        ai._post = AsyncMock(return_value={"choices": [{"finish_reason": "length", "message": {"content": '{"coverage":"YOK"}'}}]})
        with self.assertRaises(AIResponseError):
            await ai.chat_json("schema", "request")

    def test_invalid_vectors_and_rerank_results_cannot_turn_into_empty_search(self):
        for vectors in ([], [[float("nan")]], [[float("inf")]], [[0]], [[True]], [[1], [1, 2]]):
            with self.subTest(vectors=vectors), self.assertRaises(AIResponseError):
                validate_vectors(vectors, 1)
        for results in ([], [{"index": 0, "relevance_score": float("nan")}],
                        [{"index": True, "relevance_score": 1}], [{"index": 4, "relevance_score": 1}],
                        [{"index": 0, "relevance_score": 1.5}], [{"relevance_score": 0.2}]):
            with self.subTest(results=results), self.assertRaises(AIResponseError):
                validate_rerank_results(results, 2, 1)
        with self.assertRaises(AIResponseError):
            validate_rerank_results([{"index": 0, "relevance_score": .5}] * 2, 2, 2)


class RetrievalReliabilityTests(DirectoryIndexTests):
    # Reuse only setup utilities; test loader below avoids rerunning inherited tests.
    async def test_malformed_reranker_is_explicit_failure(self):
        from app import services
        self.pdf("excel.pdf")
        self.ai.rerank.side_effect = None
        self.ai.rerank.return_value = []
        with self.assertRaises(AIResponseError):
            await services.retrieve(self.db, "Need", "")

    async def test_course_scoped_chat_retrieval_filters_before_candidate_cutoff(self):
        from app import indexing, services
        self.pdf("first.pdf", pages=20)
        self.pdf("selected.pdf", "Selected course-specific contents")
        await indexing.sync_pdf_directory(self.db)
        selected = next(course for course in self.courses() if course.name == "selected")
        results = await services.retrieve(self.db, "Question", "", course_id=selected.id)
        self.assertTrue(results)
        self.assertEqual({item["chunk"].course_id for item in results}, {selected.id})

    async def test_long_course_does_not_hide_other_course_evidence(self):
        from app import services
        self.pdf("a-long.pdf", pages=20)
        self.pdf("b-small.pdf")
        self.pdf("c-small.pdf")
        results = await services.retrieve(self.db, "Question", "")
        self.assertEqual(len({item["chunk"].course_id for item in results}), 3)


def load_tests(loader, standard_tests, pattern):
    suite = unittest.TestSuite()
    for cls in (GroundingTests, ProviderOutputValidationTests, RetrievalReliabilityTests):
        for name, method in cls.__dict__.items():
            if name.startswith("test_"):
                suite.addTest(cls(name))
    return suite
