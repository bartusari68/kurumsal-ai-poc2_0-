from __future__ import annotations

import json
import shutil
from collections import defaultdict
from pathlib import Path

import fitz
from sqlalchemy import select
from sqlalchemy.orm import Session

from .ai import ai_client
from .config import settings
from .models import Course, CourseChunk, HumanReview, LearnedMapping, RequestMatch, RequestRecord
from .utils import chunk_page_text, compact_text, cosine_similarity, json_dumps, json_loads


async def ingest_pdf(db: Session, *, course_code: str, course_name: str, description: str, source_path: Path) -> Course:
    existing = db.scalar(select(Course).where(Course.code == course_code))
    if existing:
        raise ValueError(f"{course_code} kodlu ders zaten mevcut.")

    target = settings.pdf_dir / f"{course_code}_{source_path.name}"
    shutil.copyfile(source_path, target)

    course = Course(code=course_code, name=course_name, description=description, pdf_path=str(target))
    db.add(course)
    db.flush()

    doc = fitz.open(target)
    pending: list[tuple[int, int, str]] = []
    for page_idx in range(len(doc)):
        page_text = doc[page_idx].get_text("text") or ""
        chunks = chunk_page_text(page_text)
        for idx, chunk in enumerate(chunks):
            pending.append((page_idx + 1, idx, chunk))
    doc.close()

    if not pending:
        raise ValueError("PDF'den metin çıkarılamadı. Taranmış PDF ise OCR sonraki fazda eklenmeli.")

    # Ücretsiz endpoint limitlerini zorlamamak için küçük batchler.
    for start in range(0, len(pending), 24):
        batch = pending[start : start + 24]
        embeddings = await ai_client.embed([item[2] for item in batch], is_query=False)
        for (page_number, chunk_index, content), embedding in zip(batch, embeddings):
            db.add(
                CourseChunk(
                    course_id=course.id,
                    page_number=page_number,
                    chunk_index=chunk_index,
                    content=content,
                    embedding_json=json_dumps(embedding),
                    embedding_provider=ai_client.provider_name,
                )
            )
    db.commit()
    db.refresh(course)
    return course


async def retrieve(db: Session, query: str, canonical_intent: str) -> list[dict]:
    query_embedding = (await ai_client.embed([query], is_query=True))[0]
    chunks = db.scalars(
        select(CourseChunk).where(CourseChunk.embedding_provider == ai_client.provider_name)
    ).all()

    scored: list[tuple[float, CourseChunk]] = []
    for chunk in chunks:
        embedding = json_loads(chunk.embedding_json, [])
        score = cosine_similarity(query_embedding, embedding)
        scored.append((score, chunk))
    scored.sort(key=lambda x: x[0], reverse=True)
    candidates = scored[: settings.top_k_retrieve]

    learned = {
        item.course_id: item
        for item in db.scalars(select(LearnedMapping).where(LearnedMapping.canonical_intent == canonical_intent)).all()
    }

    docs = [chunk.content for _, chunk in candidates]
    reranked = await ai_client.rerank(query, docs, settings.top_k_rerank)

    results: list[dict] = []
    for rank_item in reranked:
        idx = int(rank_item.get("index", 0))
        if idx >= len(candidates):
            continue
        semantic_score, chunk = candidates[idx]
        rerank_score = float(rank_item.get("relevance_score", semantic_score))
        feedback_boost = learned.get(chunk.course_id).weight if chunk.course_id in learned else 0.0
        final_score = min(1.0, semantic_score * 0.35 + rerank_score * 0.55 + feedback_boost)
        results.append(
            {
                "chunk": chunk,
                "semantic_score": semantic_score,
                "rerank_score": rerank_score,
                "feedback_boost": feedback_boost,
                "score": final_score,
            }
        )
    results.sort(key=lambda x: x["score"], reverse=True)
    return results


async def analyze_request(db: Session, text: str) -> dict:
    classification = await ai_client.classify_request(text)
    canonical_intent = classification.get("canonical_intent", "")
    retrieved = await retrieve(db, text, canonical_intent)

    evidence: list[dict] = []
    for item in retrieved:
        chunk: CourseChunk = item["chunk"]
        course = db.get(Course, chunk.course_id)
        evidence.append(
            {
                "course_id": course.id,
                "course_code": course.code,
                "course_name": course.name,
                "page_number": chunk.page_number,
                "content": compact_text(chunk.content, 650),
                "score": item["score"],
                "semantic_score": item["semantic_score"],
                "rerank_score": item["rerank_score"],
                "feedback_boost": item["feedback_boost"],
            }
        )

    coverage = await ai_client.coverage_analysis(text, classification, evidence)
    record = RequestRecord(
        text=text,
        category=str(classification.get("category", "")),
        topic=str(classification.get("topic", "")),
        intent=str(classification.get("intent", "")),
        canonical_intent=canonical_intent,
        coverage=coverage.get("coverage", "BELIRSIZ"),
        confidence=float(coverage.get("confidence", 0.0)),
        ai_reason=str(coverage.get("reason", "")),
        missing_topics_json=json_dumps(coverage.get("missing_topics", [])),
    )
    db.add(record)
    db.flush()

    grouped: dict[int, list[dict]] = defaultdict(list)
    for e in evidence:
        grouped[e["course_id"]].append(e)
    for course_id, items in grouped.items():
        db.add(
            RequestMatch(
                request_id=record.id,
                course_id=course_id,
                score=max(i["score"] for i in items),
                evidence_json=json_dumps(items[:3]),
            )
        )
    db.commit()
    db.refresh(record)

    course_summaries = []
    for course_id, items in sorted(grouped.items(), key=lambda kv: max(x["score"] for x in kv[1]), reverse=True):
        course = db.get(Course, course_id)
        course_summaries.append(
            {
                "course_id": course.id,
                "course_code": course.code,
                "course_name": course.name,
                "score": round(max(i["score"] for i in items), 4),
                "evidence": items[:3],
            }
        )

    return {
        "request_id": record.id,
        "ai_mode": settings.ai_mode,
        "classification": classification,
        "coverage": {
            "status": record.coverage,
            "confidence": record.confidence,
            "reason": record.ai_reason,
            "missing_topics": json_loads(record.missing_topics_json, []),
        },
        "courses": course_summaries[:5],
    }


def review_request(db: Session, *, request_id: int, approved: bool, correct_course_id: int | None, comment: str) -> dict:
    request = db.get(RequestRecord, request_id)
    if not request:
        raise ValueError("Talep bulunamadı.")
    if correct_course_id is not None and not db.get(Course, correct_course_id):
        raise ValueError("Seçilen ders bulunamadı.")

    db.add(HumanReview(request_id=request_id, approved=approved, correct_course_id=correct_course_id, comment=comment))

    if correct_course_id is not None:
        mapping = db.scalar(
            select(LearnedMapping).where(
                LearnedMapping.canonical_intent == request.canonical_intent,
                LearnedMapping.course_id == correct_course_id,
            )
        )
        if mapping:
            mapping.approved_count += 1
            mapping.weight = min(0.30, 0.10 + mapping.approved_count * 0.03)
        else:
            db.add(
                LearnedMapping(
                    canonical_intent=request.canonical_intent,
                    course_id=correct_course_id,
                    approved_count=1,
                    weight=0.13,
                )
            )
    db.commit()
    return {
        "ok": True,
        "message": "İnsan değerlendirmesi kaydedildi. Doğru ders seçildiyse sonraki aynı niyetli taleplerde feedback boost uygulanacak.",
    }


async def answer_chat(db: Session, question: str, request_id: int | None, course_id: int | None) -> dict:
    query = question
    if request_id:
        request = db.get(RequestRecord, request_id)
        if request:
            query = f"{request.text}\nKullanıcı sorusu: {question}"

    results = await retrieve(db, query, "")
    evidence = []
    for item in results:
        chunk: CourseChunk = item["chunk"]
        if course_id and chunk.course_id != course_id:
            continue
        course = db.get(Course, chunk.course_id)
        evidence.append(
            {
                "course_code": course.code,
                "course_name": course.name,
                "page_number": chunk.page_number,
                "content": compact_text(chunk.content, 700),
                "score": round(item["score"], 4),
            }
        )
        if len(evidence) >= 5:
            break

    context = "\n".join(
        f"[{e['course_code']} s.{e['page_number']}] {e['content']}" for e in evidence
    )
    answer = await ai_client.chat_text(
        "Şirket içi ders asistanısın. Sadece verilen ders kanıtlarına dayan. Kanıt yoksa açıkça bulunamadığını söyle. Cevabı Türkçe, kısa ve kaynak sayfası belirterek ver.",
        f"SORU: {question}\n\nKANITLAR:\n{context or 'Kanıt bulunamadı.'}",
    )
    return {"answer": answer, "evidence": evidence, "ai_mode": settings.ai_mode}
