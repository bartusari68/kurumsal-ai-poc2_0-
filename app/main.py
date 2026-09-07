from __future__ import annotations

import os
import tempfile
import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, UploadFile, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .ai import AIResponseError, AIUnavailableError, ai_client
from .ai_errors import AIServiceError
from .local_models import local_models
from .config import settings
from .database import Base, engine, get_db, SessionLocal
from .indexing import IndexNotReadyError, active_course_ids, index_status, public_status, start_sync
from .models import Course, HumanReview, RequestDecision, RequestRecord, install_decision_guards, install_analysis_guards
from .pdf_intake import PDFIntakeError, MAX_REQUEST_BYTES, extract_request_pdf
from .schemas import AnalyzeRequest, ChatRequest, IntakeRequest, ReviewRequest, AdminLogin, StatusChange, ReferralRequest, DecisionRequest, DecisionAdvanceRequest
from .learning import record_decision, record_decision_and_advance, review_report
from .services import analyze_request, answer_chat, ingest_pdf, review_request
from .portal_auth import (ensure_admin_credentials, owner_session, require_admin, require_analyst, require_employee,
                          current_account, account_payload, is_admin, login, logout, same_origin)
from .taxonomy import public_taxonomy
from .workflow import public_result, request_detail, owned_request, request_list, change_status, refer_request

from .schemas import WorkflowActionRequest
from .workflow_core import execute_action

from .publishing_migration import install_guards as install_publication_guards, backfill as backfill_catalog
Base.metadata.create_all(bind=engine)
install_publication_guards(engine)
backfill_catalog(SessionLocal)
install_decision_guards(engine)
install_analysis_guards(engine)
from .operations import install_schema as install_operations_schema
install_operations_schema(engine)

@asynccontextmanager
async def lifespan(app):
    ensure_admin_credentials()
    from .analysis_pipeline import worker
    task = asyncio.create_task(worker(SessionLocal))
    from .operations import worker as operations_worker
    operations_task = asyncio.create_task(operations_worker(SessionLocal))
    try:
        yield
    finally:
        task.cancel()
        operations_task.cancel()
        await asyncio.gather(task, operations_task, return_exceptions=True)
        await asyncio.to_thread(local_models.close)


app = FastAPI(title="Kurumsal Öğrenme ve Yapay Zekâ", version="0.4.0", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
from .operations_api import router as operations_router
app.include_router(operations_router)
from .development_api import router as development_router
app.include_router(development_router)
from .publishing_api import router as publishing_router
app.include_router(publishing_router)


@app.middleware("http")
async def portal_boundaries(request: Request, call_next):
    if request.method in ("POST", "PUT", "PATCH", "DELETE"):
        try:
            same_origin(request)
        except HTTPException as error:
            return JSONResponse(status_code=error.status_code, content={"detail": error.detail})
    response = await call_next(request)
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    return response
app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")


@app.exception_handler(AIServiceError)
async def ai_service_error_handler(request, error: AIServiceError):
    ai_client.remember_failure(error)
    logging.getLogger(__name__).warning("AI operation failed: path=%s component=%s code=%s", request.url.path, error.payload["component"], error.payload["error_code"])
    if request.url.path in ("/api/requests/analyze", "/api/chat"):
        messages = {
            "AI_INVALID_RESPONSE": "Analiz yanıtı doğrulanamadı. Metniniz korunuyor; bağlantı durumunu kontrol edip yeniden deneyebilirsiniz.",
            "AI_TIMEOUT": "Analiz hizmeti zamanında yanıt vermedi. Metniniz korunuyor; biraz sonra yeniden deneyebilirsiniz.",
            "AI_AUTH_ERROR": "Analiz hizmetinin bağlantı ayarı kontrol edilmeli. Metniniz korunuyor; yöneticinizle iletişime geçebilirsiniz.",
            "AI_CREDIT_REQUIRED": "Analiz hizmeti şu anda kullanılamıyor. Metniniz korunuyor; yöneticinizle iletişime geçebilirsiniz.",
        }
        detail = "Analiz hizmetinin kullanım sınırına ulaşıldı. Bir süre sonra yeniden deneyebilirsiniz." if error.payload["ai_status"] == "quota" else messages.get(error.payload["error_code"], "Analiz hizmetine şu anda ulaşılamıyor. Metniniz korunuyor; biraz sonra yeniden deneyebilirsiniz.")
        return JSONResponse(status_code=error.status_code, content={"detail": detail, "ai_status": error.payload["ai_status"]})
    return JSONResponse(status_code=error.status_code, content=error.payload)


@app.exception_handler(IndexNotReadyError)
async def index_not_ready_handler(request, error: IndexNotReadyError):
    if request.url.path in ("/api/requests/analyze", "/api/chat"):
        return JSONResponse(status_code=409, content={"detail": "Eğitim içerikleri henüz hazır değil. Bir süre sonra yeniden deneyin veya yöneticinizle iletişime geçin."})
    return JSONResponse(status_code=409, content={"detail": str(error), "document_index": error.report})


@app.get("/api/documents/status", dependencies=[Depends(require_analyst)])
def documents_status(offset: int = Query(0, ge=0), limit: int = Query(20, ge=1, le=100), db: Session = Depends(get_db)):
    try:
        return public_status(index_status(db), offset=offset, limit=limit)
    except OSError as error:
        raise HTTPException(status_code=503, detail="PDF klasörü okunamıyor. PDF_DIR yolunu ve erişimini kontrol edin.") from error


@app.post("/api/documents/sync", status_code=202, dependencies=[Depends(require_analyst)])
async def documents_sync():
    return {"accepted": True, "progress": start_sync()}


@app.get("/")
def index():
    return FileResponse(Path(__file__).parent / "static" / "index_tusas_faz31.html", headers={"Cache-Control": "no-cache"})


@app.get("/api/health", dependencies=[Depends(require_analyst)])
async def health(refresh: bool = False, db: Session = Depends(get_db)):
    connection = await ai_client.healthcheck(force=refresh)
    return {
        "status": "ok",
        "ai_mode": settings.ai_mode,
        **connection,
        "llm_model": settings.llm_model if ai_client.is_available else "unavailable",
        "embedding_model": settings.embedding_model,
        "rerank_model": settings.rerank_model,
        "embedding_provider": getattr(settings, "embedding_provider", "openrouter"),
        "rerank_provider": getattr(settings, "rerank_provider", "openrouter"),
        "course_count": len(active_course_ids(db)),
        "request_count": db.scalar(select(func.count(RequestRecord.id))) or 0,
    }


@app.get("/api/courses", dependencies=[Depends(require_analyst)])
def list_courses(db: Session = Depends(get_db)):
    courses = db.scalars(select(Course).where(Course.id.in_(active_course_ids(db))).order_by(Course.code)).all()
    return [
        {"id": c.id, "code": c.code, "name": c.name, "description": c.description}
        for c in courses
    ]


@app.post("/api/courses/upload", dependencies=[Depends(require_analyst)])
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
            total_bytes = 0
            while chunk := await file.read(1024 * 1024):
                total_bytes += len(chunk)
                if total_bytes > 30 * 1024 * 1024:
                    raise HTTPException(413, "Ders PDF'i en fazla 30 MB olabilir.")
                out.write(chunk)
        course = await ingest_pdf(
            db,
            course_code=course_code.strip().upper(),
            course_name=course_name.strip(),
            description=description.strip(),
            source_path=tmp_path,
        )
        return {"ok": True, "course": {"id": course.id, "code": course.code, "name": course.name}}
    except HTTPException:
        db.rollback()
        raise
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except AIUnavailableError as exc:
        db.rollback()
        raise HTTPException(status_code=503, detail="Yapay zekâ bağlantısı kapalı. PDF indekslenemedi.") from exc
    except AIServiceError:
        db.rollback()
        raise
    except (AIResponseError, httpx.HTTPError) as exc:
        db.rollback()
        raise HTTPException(status_code=502, detail="Yapay zekâ servisi PDF'yi indeksleyemedi.") from exc
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail="PDF indeksleme sırasında beklenmeyen bir hata oluştu.") from exc
    finally:
        tmp_path.unlink(missing_ok=True)
        await file.close()


_pdf_intake_limit = asyncio.Semaphore(2)


@app.post("/api/requests/extract-pdf", dependencies=[Depends(require_employee)])
async def extract_request_attachment(file: UploadFile = File(...)):
    try:
        data = await file.read(MAX_REQUEST_BYTES + 1)
        if len(data) > MAX_REQUEST_BYTES:
            raise HTTPException(413, "Talep eki en fazla 10 MB olabilir.")
        async with _pdf_intake_limit:
            return await asyncio.to_thread(extract_request_pdf, data, file.filename or "")
    except PDFIntakeError as error:
        raise HTTPException(422, str(error)) from error
    finally:
        await file.close()


@app.post("/api/requests/analyze", status_code=202)
def analyze(payload: AnalyzeRequest, db: Session = Depends(get_db), session=Depends(require_employee)):
    from .analysis_pipeline import persist_request
    from .intake import submission_metadata
    metadata = submission_metadata(payload.intake_token, session.token_hash)
    record, flow = persist_request(db, payload.text, session, payload.idempotency_key, intake_metadata=metadata)
    result = request_detail(db, record, flow)
    result["message"] = "Talebiniz kaydedildi. Analiz durumu talep detayından takip edilebilir."
    return result


@app.post("/api/intake")
async def intake(payload: IntakeRequest, session=Depends(require_employee)):
    from .intake import clarify
    return await clarify(payload, session.token_hash)


@app.post("/api/reviews", dependencies=[Depends(require_analyst)])
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
async def chat(payload: ChatRequest, db: Session = Depends(get_db), session=Depends(require_employee)):
    try:
        if payload.request_id:
            owned_request(db, payload.request_id, session.token_hash)
        return await answer_chat(db, payload.question, payload.request_id, payload.course_id)
    except HTTPException:
        raise
    except IndexNotReadyError:
        db.rollback()
        raise
    except AIUnavailableError as exc:
        raise HTTPException(status_code=503, detail="Yapay zekâ bağlantısı kapalı. Sohbet başlatılamadı.") from exc
    except AIServiceError:
        db.rollback()
        raise
    except AIResponseError as exc:
        raise AIServiceError("Yapay zekâ yanıtı doğrulanamadı. Lütfen tekrar deneyin.", code="AI_INVALID_RESPONSE", component="chat") from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="Yapay zekâ servisine şu anda ulaşılamıyor.") from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Sohbet sırasında beklenmeyen bir hata oluştu.") from exc


@app.get("/api/dashboard", dependencies=[Depends(require_analyst)])
def dashboard(db: Session = Depends(get_db)):
    total_requests = db.scalar(select(func.count(RequestRecord.id))) or 0
    legacy_reviews = db.scalar(select(func.count(HumanReview.id))) or 0
    decisions = db.scalar(select(func.count(RequestDecision.id))) or 0
    coverage_counts = dict(
        db.execute(select(RequestRecord.coverage, func.count(RequestRecord.id)).group_by(RequestRecord.coverage)).all()
    )
    return {
        "courses": len(active_course_ids(db)),
        "requests": total_requests,
        "reviews": legacy_reviews + decisions,
        "legacy_reviews": legacy_reviews,
        "decision_events": decisions,
        "reviewed_requests": db.scalar(select(func.count(func.distinct(RequestDecision.request_id)))) or 0,
        "var": coverage_counts.get("VAR", 0),
        "kismen": coverage_counts.get("KISMEN_VAR", 0),
        "yok": coverage_counts.get("YOK", 0),
    }


@app.get("/api/portal/session")
def session_info(account=Depends(current_account)):
    return account_payload(account)


@app.post("/api/auth/login")
@app.post("/api/admin/login")
def account_login(payload: AdminLogin, request: Request, response: Response, db: Session = Depends(get_db)):
    return login(request, response, payload.username, payload.password, db)


@app.post("/api/auth/logout")
@app.post("/api/admin/logout")
def account_logout(request: Request, response: Response, db: Session = Depends(get_db)):
    return logout(request, response, db)


@app.get("/api/portal/health", dependencies=[Depends(owner_session)])
async def employee_health(refresh: bool = False):
    result = await ai_client.healthcheck(force=refresh)
    return {"ai_status": result.get("ai_status", "error"), "detail": "Bağlantı kontrolü başarılı. Talebinizi gönderebilirsiniz." if result.get("ai_status") == "connected" else "Analiz hizmeti şu anda hazır değil. Biraz sonra yeniden deneyebilirsiniz."}


@app.post("/api/portal/prepare", status_code=202, dependencies=[Depends(require_employee)])
async def employee_prepare():
    start_sync()
    return {"accepted": True}


@app.get("/api/portal/preparation", dependencies=[Depends(require_employee)])
def employee_preparation(db: Session = Depends(get_db)):
    try:
        report = public_status(index_status(db))
        return {"ready": report["complete"], "running": report["progress"]["running"], "failed": bool(report["error_count"] or report["progress"]["error"])}
    except OSError:
        return {"ready": False, "running": False, "failed": True}


@app.get("/api/taxonomy", dependencies=[Depends(require_admin)])
def taxonomy():
    return public_taxonomy()


@app.get("/api/requests/mine")
def my_requests(view: str = Query("", max_length=20), status: str | None = None, search: str = Query("", max_length=100), sort: str = Query("newest", pattern="^(newest|oldest|updated)$"), offset: int = Query(0, ge=0), limit: int = Query(20, ge=1, le=100), session=Depends(require_employee), db: Session = Depends(get_db)):
    return request_list(db, session.token_hash, status=status, search=search, sort=sort, offset=offset, limit=limit, view=view, user_id=session.user_id)


@app.get("/api/requests/{request_id}")
def my_request(request_id: int, session=Depends(require_employee), db: Session = Depends(get_db)):
    record, flow = owned_request(db, request_id, session.token_hash)
    return {**request_detail(db, record, flow), 'acting_delegation': session.delegation}


@app.patch("/api/requests/{request_id}/status")
def my_request_status(request_id: int, payload: StatusChange, session=Depends(require_employee), db: Session = Depends(get_db)):
    record, flow = owned_request(db, request_id, session.token_hash)
    return change_status(db, record, flow, owner_hash=session.token_hash, admin=False, target=payload.status, note=payload.note, expected_version=payload.expected_version, principal=session)


@app.get("/api/admin/requests")
def admin_requests(view: str = Query("", max_length=20), status: str | None = None, search: str = Query("", max_length=100), sort: str = Query("newest", pattern="^(newest|oldest|updated)$"), offset: int = Query(0, ge=0), limit: int = Query(20, ge=1, le=100), session=Depends(require_admin), db: Session = Depends(get_db)):
    return request_list(db, session.token_hash, admin=True, role=session.role, status=status, search=search, sort=sort, offset=offset, limit=limit, view=view, user_id=session.user_id)


@app.get("/api/admin/requests/{request_id}")
def admin_request(request_id: int, session=Depends(require_admin), db: Session = Depends(get_db)):
    record, flow = owned_request(db, request_id, session.token_hash, admin=True, role=session.role)
    return {**request_detail(db, record, flow, admin=session.role == "NEEDS_ANALYST", role=session.role), 'acting_delegation': session.delegation}


@app.patch("/api/admin/requests/{request_id}/status")
def admin_request_status(request_id: int, payload: StatusChange, session=Depends(require_admin), db: Session = Depends(get_db)):
    record, flow = owned_request(db, request_id, session.token_hash, admin=True, role=session.role)
    return change_status(db, record, flow, owner_hash=session.token_hash, admin=True, role=session.role, target=payload.status, note=payload.note, expected_version=payload.expected_version, principal=session)

@app.post("/api/admin/requests/{request_id}/refer")
def admin_refer(request_id: int, payload: ReferralRequest, session=Depends(require_analyst), db: Session = Depends(get_db)):
    record, flow = owned_request(db, request_id, session.token_hash, admin=True, role=session.role)
    return refer_request(db, record, flow, session, payload.department, payload.analysis_summary,
                         payload.training_need_confirmed, payload.expected_version)


@app.post("/api/admin/requests/{request_id}/decisions")
def admin_decision(request_id: int, payload: DecisionRequest, session=Depends(require_admin), db: Session = Depends(get_db)):
    record, flow = owned_request(db, request_id, session.token_hash, admin=True, role=session.role)
    return record_decision(db, record, flow, session, payload)


@app.post("/api/admin/requests/{request_id}/review-and-advance")
def admin_review_and_advance(request_id: int, payload: DecisionAdvanceRequest, session=Depends(require_analyst), db: Session = Depends(get_db)):
    record, flow = owned_request(db, request_id, session.token_hash, admin=True, role=session.role)
    return record_decision_and_advance(db, record, flow, session, payload)


@app.get("/api/admin/review-report")
def admin_review_report(session=Depends(require_admin), db: Session = Depends(get_db)):
    return review_report(db, session)


@app.post("/api/requests/{request_id}/actions")
def employee_action(request_id: int, payload: WorkflowActionRequest, session=Depends(require_employee), db: Session = Depends(get_db)):
    record, flow = owned_request(db, request_id, session.token_hash)
    return execute_action(db, record, flow, session, payload)


@app.post("/api/admin/requests/{request_id}/actions")
def manager_action(request_id: int, payload: WorkflowActionRequest, session=Depends(require_admin), db: Session = Depends(get_db)):
    record, flow = owned_request(db, request_id, session.token_hash, admin=True, role=session.role)
    return execute_action(db, record, flow, session, payload)


from .schemas import AnalysisRetryRequest

@app.post("/api/requests/{request_id}/analysis", status_code=202)
def employee_analysis(request_id: int, payload: AnalysisRetryRequest, session=Depends(require_employee), db: Session = Depends(get_db)):
    from .analysis_pipeline import request_analysis
    record, flow = owned_request(db, request_id, session.token_hash)
    return request_analysis(db, record, flow, session, payload)


@app.post("/api/admin/requests/{request_id}/analysis", status_code=202)
def analyst_analysis(request_id: int, payload: AnalysisRetryRequest, session=Depends(require_analyst), db: Session = Depends(get_db)):
    from .analysis_pipeline import request_analysis
    record, flow = owned_request(db, request_id, session.token_hash, admin=True, role=session.role)
    return request_analysis(db, record, flow, session, payload)
