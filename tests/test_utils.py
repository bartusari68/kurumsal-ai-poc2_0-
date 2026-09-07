import unittest

from app.utils import canonicalize, chunk_page_text, cosine_similarity, demo_embedding


class UtilityTests(unittest.TestCase):
    def test_canonicalize(self):
        self.assertEqual(canonicalize("Excel Yetkinlik Geliştirme"), "excel_yetkinlik_gelistirme")

    def test_chunking(self):
        chunks = chunk_page_text("A" * 4000, max_chars=1000, overlap=100)
        self.assertGreaterEqual(len(chunks), 4)

    def test_legacy_hash_vector_similarity(self):
        a = demo_embedding("excel pivot tablo")
        b = demo_embedding("excel pivot tablo eğitimi")
        c = demo_embedding("forklift bakım prosedürü")
        self.assertGreater(cosine_similarity(a, b), cosine_similarity(a, c))


if __name__ == "__main__":
    unittest.main()
