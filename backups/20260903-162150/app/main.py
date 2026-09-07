from __future__ import annotations

import os
import tempfile
from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .config import settings
from .database import Base, engine, get_db
from .models import Course, HumanReview, RequestRecord
from .schemas import AnalyzeRequest, ChatRequest, ReviewRequest
from .services import analyze_request, answer_chat, ingest_pdf, review_request

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Kurumsal AI POC", version="0.1.0")
app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")


@app.get("/")
def index():
    return FileResponse(Path(__file__).parent / "static" / "index.html")


@app.get("/api/health")
def health(db: Session = Depends(get_db)):
    return {
        "status": "ok",
        "ai_mode": settings.ai_mode,
        "llm_model": settings.llm_model if settings.openrouter_api_key else "demo-fallback",
        "embedding_model": settings.embedding_model if settings.openrouter_api_key else "demo-hash-v1",
        "course_count": db.scalar(select(func.count(Course.id))) or 0,
        "request_count": db.scalar(select(func.count(RequestRecord.id))) or 0,
    }


@app.get("/api/courses")
def list_courses(db: Session = Depends(get_db)):
    courses = db.scalars(select(Course).order_by(Course.code)).all()
    return [
        {"id": c.id, "code": c.code, "name": c.name, "description": c.description}
        for c in courses
    ]


@app.post("/api/courses/upload")
async def upload_course(
    course_code: str = Form(...),
    course_name: str = Form(...),
    description: str = Form(""),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Yalnızca PDF yüklenebilir.")
    suffix = Path(file.filename).suffix
    fd, tmp_name = tempfile.mkstemp(suffix=suffix)
    os.close(fd)
    tmp_path = Path(tmp_name)
    try:
        with tmp_path.open("wb") as out:
            while chunk := await file.read(1024 * 1024):
                out.write(chunk)
        course = await ingest_pdf(
            db,
            course_code=course_code.strip().upper(),
            course_name=course_name.strip(),
            description=description.strip(),
            source_path=tmp_path,
        )
        return {"ok": True, "course": {"id": course.id, "code": course.code, "name": course.name}}
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"PDF indeksleme hatası: {exc}") from exc
    finally:
        tmp_path.unlink(missing_ok=True)


@app.post("/api/requests/analyze")
async def analyze(payload: AnalyzeRequest, db: Session = Depends(get_db)):
    try:
        return await analyze_request(db, payload.text)
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Analiz hatası: {exc}") from exc


@app.post("/api/reviews")
def review(payload: ReviewRequest, db: Session = Depends(get_db)):
    try:
        return review_request(
            db,
            request_id=payload.request_id,
            approved=payload.approved,
            correct_course_id=payload.correct_course_id,
            comment=payload.comment,
        )
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/chat")
async def chat(payload: ChatRequest, db: Session = Depends(get_db)):
    try:
        return await answer_chat(db, payload.question, payload.request_id, payload.course_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Chat hatası: {exc}") from exc


@app.get("/api/dashboard")
def dashboard(db: Session = Depends(get_db)):
    total_requests = db.scalar(select(func.count(RequestRecord.id))) or 0
    reviews = db.scalar(select(func.count(HumanReview.id))) or 0
    coverage_counts = dict(
        db.execute(select(RequestRecord.coverage, func.count(RequestRecord.id)).group_by(RequestRecord.coverage)).all()
    )
    return {
        "courses": db.scalar(select(func.count(Course.id))) or 0,
        "requests": total_requests,
        "reviews": reviews,
        "var": coverage_counts.get("VAR", 0),
        "kismen": coverage_counts.get("KISMEN_VAR", 0),
        "yok": coverage_counts.get("YOK", 0),
    }
