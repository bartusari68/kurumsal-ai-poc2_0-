"""Read-only request diagnostic; synthetic input, no request record or raw model output."""
import asyncio
import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.ai import ai_client
from app import services
from app.database import Base
from app.models import Course, CourseChunk, RequestRecord, RequestWorkflow
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session


async def main():
    original_post = ai_client._post
    stage = "classification"

    async def traced_post(endpoint, payload, component, timeout):
        data = await original_post(endpoint, payload, component, timeout)
        if component == "analysis":
            print(json.dumps({"stage": stage, "choices": [
                {"finish_reason": c.get("finish_reason"), "characters": len(c.get("message", {}).get("content") or "")}
                for c in data.get("choices", [])], "usage": data.get("usage", {})}), flush=True)
        return data

    ai_client._post = traced_post
    text = "Sentetik test: Fizik dersinde itki konusunu anlamadım, bu konuda desteğe ihtiyacım var."
    try:
        classification = await ai_client.classify_request(text)
        print(json.dumps({"classification_valid": True, "needs": len(classification["requirements"])}), flush=True)
        # Entirely authored fixtures: never read or transmit local PDFs or database content.
        evidence = [{"evidence_id": f"E{i+1}", "course_code": f"SYNTHETIC-{i+1}",
                     "course_name": name, "content": content, "score": 0.8 - i * 0.1}
                    for i, (name, content) in enumerate([
                        ("Sentetik Mekanik Dersi", "İtki kuvvetin zaman boyunca etkisidir. Momentum değişimi ile ilişkisi, kuvvet-zaman grafikleri ve örnek problemler işlenir."),
                        ("Sentetik Matematik Dersi", "İntegral, eğri altındaki alan ve temel türev konuları örneklerle anlatılır."),
                        ("Sentetik Uçuş Dersi", "İtki kuvveti, sürükleme, kaldırma ve ağırlık tanıtılır. Motorun uçağı hareket ettirmesi incelenir.")])]
        if "--unrelated" in sys.argv:
            evidence = [{"evidence_id": f"E{i+1}", "course_code": f"SYNTHETIC-{i+1}",
                         "course_name": f"Sentetik {name} Dersi", "content": content, "score": 0.2}
                        for i, (name, content) in enumerate([
                            ("Excel", "Pivot tablo ile veriler özetlenir. Power Query ile tablolar birleştirilir."),
                            ("Python", "Dosya otomasyonu, döngüler, değişkenler ve temel veri yapıları anlatılır."),
                            ("C++", "Akıllı işaretçiler, bellek yönetimi, eşzamanlılık ve yazılım performansı anlatılır.")])]
        stage = "coverage"
        coverage = await ai_client.coverage_analysis(text, classification, evidence)
        assessments = {i.get("course_code") for i in coverage["course_assessments"] if isinstance(i, dict)}
        print(json.dumps({"coverage_valid": True, "decision": coverage["coverage"], "assessments": len(assessments),
                          "matching_assessment": any(i["course_code"] in assessments for i in evidence)}), flush=True)
        # Exercise the real persistence/scoring service with the above real model
        # responses, but synthetic retrieval and a disposable in-memory database.
        stage = "isolated_request_persistence"
        engine = create_engine("sqlite://")
        Base.metadata.create_all(engine)
        try:
            with Session(engine) as db:
                candidates = []
                for item in evidence:
                    course = Course(code=item["course_code"], name=item["course_name"], pdf_path="synthetic-fixture-only")
                    db.add(course)
                    db.flush()
                    chunk = CourseChunk(course_id=course.id, page_number=1, chunk_index=0, content=item["content"])
                    candidates.append({"chunk": chunk, "score": item["score"], "semantic_score": .5, "rerank_score": .5, "feedback_boost": 0})
                with patch.object(services, "sync_pdf_directory", AsyncMock(return_value={"complete": True})), \
                     patch.object(services, "retrieve", AsyncMock(return_value=candidates)), \
                     patch.object(services, "assert_sources_current"), \
                     patch.object(ai_client, "classify_request", AsyncMock(return_value=classification)), \
                     patch.object(ai_client, "coverage_analysis", AsyncMock(return_value=coverage)):
                    result = await services.analyze_request(db, text, owner_hash="user:synthetic")
                flow = db.get(RequestWorkflow, result["request_id"])
                assert flow.status == "IN_REVIEW" and flow.owner_hash == "user:synthetic"
                assert db.scalar(select(func.count(RequestRecord.id))) == 1
                if coverage["coverage"] == "YOK":
                    assert result["coverage"]["fit_percent"] == 0 and result["courses"] == []
                print(json.dumps({"saved_in_memory_only": True, "status": flow.status,
                                  "fit_percent": result["coverage"]["fit_percent"], "recommended_courses": len(result["courses"])}), flush=True)
        finally:
            engine.dispose()
    except Exception as error:
        print(json.dumps({"failed_stage": stage, "error_type": type(error).__name__,
                          "detail": str(error) if type(error).__name__ in ("AIResponseError", "AIServiceError") else "See exception type"}, ensure_ascii=True), flush=True)
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
