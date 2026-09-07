from app.utils import canonicalize, chunk_page_text, cosine_similarity, demo_embedding


def test_canonicalize():
    assert canonicalize("Excel Yetkinlik Geliştirme") == "excel_yetkinlik_gelistirme"


def test_chunking():
    chunks = chunk_page_text("A" * 4000, max_chars=1000, overlap=100)
    assert len(chunks) >= 4


def test_demo_embedding_similarity():
    a = demo_embedding("excel pivot tablo")
    b = demo_embedding("excel pivot tablo eğitimi")
    c = demo_embedding("forklift bakım prosedürü")
    assert cosine_similarity(a, b) > cosine_similarity(a, c)
