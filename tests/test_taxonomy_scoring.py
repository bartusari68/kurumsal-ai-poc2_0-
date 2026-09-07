import asyncio
import unittest
from unittest.mock import AsyncMock
from app.ai import AIClient
from app.scoring import course_fit, retrieval_rank, unit
from app.taxonomy import INDEX, TAXONOMY, normalize_category, public_taxonomy


class TaxonomyTests(unittest.TestCase):
    def test_unique_bounded_categories(self):
        self.assertEqual(len(TAXONOMY), 11)
        self.assertEqual(len(INDEX), 34)
        self.assertTrue(all(group["boundary"] for group in TAXONOMY))
        self.assertNotEqual(normalize_category("SOFTWARE.CPP"), normalize_category("SOFTWARE.DOTNET"))
        self.assertNotEqual(normalize_category("DATA.EXCEL")["category_id"], normalize_category("SOFTWARE.PYTHON")["category_id"])
        self.assertEqual(normalize_category("UNTRUSTED.CATEGORY")["subcategory_id"], "OTHER.REVIEW")
        self.assertEqual(len(public_taxonomy()["groups"]), 11)

    def test_classification_uses_server_labels_and_bounded_deduplicated_needs(self):
        ai = AIClient()
        ai.chat_json = AsyncMock(return_value={"subcategory_id": "SOFTWARE.CPP", "category": "Invented", "topic": "Concurrency", "intent": "Training", "learning_needs": ["Mutex", "Mutex", "Atomics"], "secondary_categories": ["DATA.EXCEL", "Invented", "DATA.EXCEL"]})
        result = asyncio.run(ai.classify_request("C++ mutex and atomics"))
        self.assertEqual(result["category"], "Yazılım Geliştirme ve Otomasyon")
        self.assertEqual(result["requirements"], [{"id": "N1", "label": "Mutex"}, {"id": "N2", "label": "Atomics"}])
        self.assertEqual(len(result["secondary_categories"]), 1)

    def test_unknown_and_critical_cases_require_human_review(self):
        for subcategory, risk in [("INVALID", "NORMAL"), ("SAFETY.OHS", "KRITIK")]:
            ai = AIClient()
            ai.chat_json = AsyncMock(return_value={"subcategory_id": subcategory, "topic": "Topic", "intent": "Need", "human_review_required": False, "risk_level": risk})
            result = asyncio.run(ai.classify_request("Synthetic"))
            self.assertTrue(result["human_review_required"])
            if risk == "KRITIK":
                self.assertEqual(result["recommended_action"], "ACIL_INCELEME")


class ScoringTests(unittest.TestCase):
    def setUp(self):
        self.needs = [{"id": "N1", "label": "Pivot"}, {"id": "N2", "label": "Power Query"}]
        self.evidence = [{"evidence_id": "E1", "semantic_score": 1, "rerank_score": 1}]

    def fit(self, outcomes):
        return course_fit(self.needs, {"needs": outcomes, "summary": "Synthetic", "topics": ["Excel"]}, self.evidence)

    def test_full_coverage_is_100_and_breakdown_sums_to_percentage(self):
        result = self.fit([["N1", "FULL", ["E1"]], ["N2", "FULL", ["E1"]]])
        self.assertEqual(result["percent"], 100)
        self.assertEqual(sum(result["components"].values()), 100)
        self.assertIn("olasılığı değildir", result["explanation"])

    def test_partial_and_missing_needs_reduce_percentage(self):
        result = self.fit([["N1", "FULL", ["E1"]], ["N2", "PARTIAL", ["E1"]]])
        self.assertEqual(result["components"]["need_coverage"], 52.5)
        self.assertLess(result["percent"], 100)
        self.assertLess(self.fit([["N1", "FULL", ["E1"]]])["percent"], result["percent"])

    def test_foreign_evidence_empty_or_duplicate_requirements_cannot_inflate_score(self):
        self.assertEqual(self.fit([["N1", "FULL", ["OTHER_COURSE"]]])["percent"], 0)
        self.assertEqual(self.fit([["N1", "FULL", []]])["percent"], 0)
        self.assertEqual(self.fit([["N9", "FULL", ["E1"]]])["percent"], 0)
        once = self.fit([["N1", "FULL", ["E1"]]])
        self.assertEqual(once, self.fit([["N1", "FULL", ["E1"]], ["N1", "FULL", ["E1"]]]))

    def test_feedback_never_enters_fit_and_numeric_values_are_safe(self):
        original = self.fit([["N1", "FULL", ["E1"]]])
        self.evidence[0]["feedback_boost"] = 100
        self.assertEqual(original, self.fit([["N1", "FULL", ["E1"]]]))
        for value in (float("nan"), float("inf"), "bad", None, -10):
            self.assertEqual(unit(value), 0)
        self.assertEqual(unit(7), 1)
        self.assertLessEqual(retrieval_rank(.3, .4, 100) - retrieval_rank(.3, .4), .050001)

    def test_no_needs_or_no_support_is_zero(self):
        self.assertEqual(course_fit([], {}, self.evidence)["percent"], 0)
        self.assertEqual(self.fit([])["percent"], 0)
