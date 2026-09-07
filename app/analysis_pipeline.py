"""Durable request intake, immutable analysis snapshots and fenced execution.

The HTTP layer only commits work. Execution is independently callable by the local
worker (or a future queue). No model call holds a workflow write transaction open.
"""
from .time_policy import utc_now, as_utc, utc_stamp
import asyncio
import hashlib
import logging
import uuid
from datetime import datetime, timedelta

import httpx
from fastapi import HTTPException
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError

from .models import (AnalysisRun, DecisionAnalysisLink, DocumentIndex, PortalUser,
    RequestEvent, RequestEventAction, RequestRecord, RequestSubmission, RequestWorkflow)
from .utils import json_dumps, json_loads

LABELS = {"PENDING": "Analiz bekliyor", "PROCESSING": "Analiz ediliyor", "COMPLETED": "Analiz tamamlandı", "FAILED": "Analiz tamamlanamadı"}
ACTIVE = ("PENDING", "PROCESSING")
LEASE_SECONDS = 90
EXECUTION_TIMEOUT = 12 * 60
logger = logging.getLogger(__name__)


def latest_run(db, request_id, completed=False):
    query = select(AnalysisRun).where(AnalysisRun.request_id == request_id)
    if completed:
        query = query.where(AnalysisRun.status == "COMPLETED")
    return db.scalar(query.order_by(AnalysisRun.sequence.desc()).limit(1))


def current_result(db, record, flow):
    run = latest_run(db, record.id, completed=True)
    return json_loads(run.result_json, {}) if run else json_loads(flow.result_json, {}) if flow else {}


def additional_events(db, request_id):
    # Reuse the existing, immutable employee event. Snapshot IDs reference exact notes.
    return db.scalars(select(RequestEvent).join(RequestEventAction).where(RequestEvent.request_id == request_id,
        RequestEvent.actor == "EMPLOYEE", RequestEventAction.action == "PROVIDE_INFO").order_by(RequestEvent.id)).all()


def input_snapshot(db, record, flow):
    return {"original_request": record.text, "additional_event_ids": [event.id for event in additional_events(db, record.id)],
            "request_version": flow.version, "index_snapshot_phase": "ENQUEUE",
            "index_sources": [{"course_id": row.course_id, "fingerprint": row.content_hash,
                "embedding_identity": row.embedding_provider, "pipeline_version": row.pipeline_version}
                for row in db.scalars(select(DocumentIndex).where(DocumentIndex.status == "ready").order_by(DocumentIndex.course_id))]}


def input_text(db, snapshot, request_id):
    ids = snapshot.get("additional_event_ids", [])
    notes = db.scalars(select(RequestEvent.note).where(RequestEvent.request_id == request_id,
        RequestEvent.id.in_(ids)).order_by(RequestEvent.id)).all()
    if len(notes) != len(ids):
        raise ValueError("Referenced input event missing")
    return snapshot["original_request"] + ("\n\nTalep sahibinin ek bilgileri:\n" + "\n\n".join(notes) if notes else "")


def ensure_baseline(db, record, flow):
    """Lazy additive import: no startup rewrite or fabricated completion timestamp."""
    if latest_run(db, record.id) or not flow or not json_loads(flow.result_json, {}):
        return
    db.add(AnalysisRun(request_id=record.id, sequence=1, status="COMPLETED", trigger="IMPORTED",
        input_json=json_dumps({"original_request": record.text, "additional_event_ids": [], "request_version": None,
                              "source": "existing_workflow_snapshot"}), result_json=flow.result_json,
        canonical_intent=record.canonical_intent or "", created_at=record.created_at))
    db.flush()


def decision_reference(db, decision):
    link = db.get(DecisionAnalysisLink, decision.id)
    run = db.get(AnalysisRun, link.analysis_run_id) if link else None
    return {"id": run.id, "sequence": run.sequence, "legacy": run.trigger == "IMPORTED"} if run else {"id": None, "sequence": None, "legacy": True}


def decision_is_current(db, decision, record, flow):
    run = latest_run(db, record.id, completed=True)
    link = db.get(DecisionAnalysisLink, decision.id) if decision else None
    if not decision:
        return False
    if not run:
        return link is None
    return link.analysis_run_id == run.id if link else run.trigger == "IMPORTED"


def review_ready(db, record, flow):
    latest = latest_run(db, record.id)
    if not latest:
        return True  # Preserve legacy manual review behavior.
    if latest.status in ACTIVE:
        return False
    successful = latest_run(db, record.id, completed=True)
    if not successful:
        return False
    return json_loads(successful.input_json, {}).get("additional_event_ids", []) == [row.id for row in additional_events(db, record.id)]


def describe_run(run):
    if not run:
        return None
    from .workflow import stamp
    return {"id": run.id, "sequence": run.sequence, "status": run.status, "status_label": LABELS[run.status],
            "trigger": run.trigger, "created_at": stamp(run.created_at), "started_at": stamp(run.started_at),
            "completed_at": stamp(run.completed_at), "error_code": run.error_code, "error_message": run.error_message,
            "retry_of": run.retry_of, "imported": run.trigger == "IMPORTED"}


def analysis_actions(db, record, flow, role):
    if (flow and flow.status != "IN_REVIEW") or (not flow and role != "NEEDS_ANALYST") or role not in ("EMPLOYEE", "NEEDS_ANALYST"):
        return []
    latest = latest_run(db, record.id)
    if latest and latest.status in ACTIVE:
        return []
    return [{"code": "RETRY" if latest and latest.status == "FAILED" else "REANALYZE",
             "label": "Analizi yeniden dene" if latest and latest.status == "FAILED" else "Yeniden analiz et"}]


def analysis_projection(db, record, flow, role):
    latest, completed = latest_run(db, record.id), latest_run(db, record.id, completed=True)
    if not latest:
        return {"latest_run": None, "latest_completed": None, "legacy_result": bool(json_loads(flow.result_json, {})) if flow else False,
                "available_actions": analysis_actions(db, record, flow, role), "history": []}
    return {"latest_run": describe_run(latest), "latest_completed": describe_run(completed),
            "legacy_result": bool(completed and completed.trigger == "IMPORTED"),
            "result_is_current_input": review_ready(db, record, flow),
            "available_actions": analysis_actions(db, record, flow, role),
            "history": [describe_run(row) for row in db.scalars(select(AnalysisRun).where(AnalysisRun.request_id == record.id).order_by(AnalysisRun.sequence.desc()).limit(20))]}


def analysis_event(db, run, label, action):
    from .process import add_process_event
    flow = db.get(RequestWorkflow, run.request_id)
    add_process_event(db, request_id=run.request_id, status=flow.status, actor="SYSTEM", note=label,
        action=action, from_status=flow.status, details={"analysis_run_id": run.id, "analysis_sequence": run.sequence, "trigger": run.trigger})


def enqueue(db, record, flow, *, trigger, user_id=None, key=None, retry_of=None):
    # Caller owns the workflow version lock and the enclosing transaction.
    active = db.scalar(select(AnalysisRun).where(AnalysisRun.active_request_id == record.id))
    if active:
        return active
    ensure_baseline(db, record, flow)
    sequence = (db.scalar(select(func.max(AnalysisRun.sequence)).where(AnalysisRun.request_id == record.id)) or 0) + 1
    run = AnalysisRun(request_id=record.id, active_request_id=record.id, sequence=sequence, status="PENDING",
        trigger=trigger, triggered_by=user_id, idempotency_key=key, retry_of=retry_of,
        input_json=json_dumps(input_snapshot(db, record, flow)))
    db.add(run)
    db.flush()
    analysis_event(db, run, f"Analiz sürümü {sequence} sıraya alındı." + (" Ek bilgiler değerlendirmeye dahil edildi." if trigger == "EXTRA_INFO" else ""), "ANALYSIS_QUEUED")
    return run


def persist_request(db, text, principal, key, *, intake_metadata=None):
    text = text.strip()
    if not 3 <= len(text) <= 5000:
        raise HTTPException(422, "Talep 3–5000 karakter içermelidir.")
    key = key or str(uuid.uuid4())  # Compatibility clients; browser always supplies a stable key.
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    def receipt():
        return db.scalar(select(RequestSubmission).where(RequestSubmission.owner_hash == principal.token_hash,
                                                        RequestSubmission.idempotency_key == key))
    previous = receipt()
    if previous:
        if previous.text_hash != digest:
            raise HTTPException(409, "Bu gönderim anahtarı farklı bir talep için kullanılmış. Yeni gönderim başlatın.")
        return db.get(RequestRecord, previous.request_id), db.get(RequestWorkflow, previous.request_id)
    try:
        record = RequestRecord(text=text)
        db.add(record)
        db.flush()
        flow = RequestWorkflow(request_id=record.id, owner_hash=principal.token_hash, status="IN_REVIEW", version=1, result_json="{}")
        db.add(flow)
        db.add(RequestSubmission(request_id=record.id, owner_hash=principal.token_hash, idempotency_key=key, text_hash=digest))
        db.flush()
        from .process import add_process_event
        add_process_event(db, request_id=record.id, status=flow.status, actor="EMPLOYEE", principal=principal,
                          note="Talep kalıcı olarak kaydedildi; AI değerlendirmesi henüz tamamlanmadı.", action="REQUEST_SAVED", from_status=flow.status,
                          details=intake_metadata)
        enqueue(db, record, flow, trigger="INITIAL", user_id=principal.user_id, key=key)
        db.commit()
        return record, flow
    except IntegrityError:
        db.rollback()
        previous = receipt()
        if previous and previous.text_hash == digest:
            return db.get(RequestRecord, previous.request_id), db.get(RequestWorkflow, previous.request_id)
        raise HTTPException(409, "Gönderim başka bir işlemde kaydedildi. Talep listenizi yenileyin.")


def request_analysis(db, record, flow, principal, payload):
    from .workflow import owned_request, request_detail
    from .workflow_core import lock_flow
    owned_request(db, record.id, principal.token_hash, admin=principal.role != "EMPLOYEE", role=principal.role)
    if principal.role not in ("EMPLOYEE", "NEEDS_ANALYST"):
        raise HTTPException(403, "Yeniden analiz için yetkiniz yok.")
    key = payload.idempotency_key
    previous = db.scalar(select(AnalysisRun).where(AnalysisRun.request_id == record.id, AnalysisRun.idempotency_key == key))
    if previous:
        return request_detail(db, record, flow, admin=principal.role == "NEEDS_ANALYST", role=principal.role)
    if flow and flow.status != "IN_REVIEW":
        raise HTTPException(422, "Yeniden analiz için talep ihtiyaç analizinde olmalıdır.")
    if flow and db.scalar(select(AnalysisRun.id).where(AnalysisRun.active_request_id == record.id)):
        return request_detail(db, record, flow, admin=principal.role == "NEEDS_ANALYST", role=principal.role)
    if payload.expected_version != (flow.version if flow else 0):
        raise HTTPException(409, "Talep güncellendi. Güncel kaydı açın.")
    try:
        if not flow:
            from .workflow_policy import authorize
            authorize(db, record, flow, principal.role, "START_REVIEW", payload.expected_version)
        previous = latest_run(db, record.id)
        flow = lock_flow(db, record, flow, payload.expected_version)
        enqueue(db, record, flow, trigger="RETRY" if previous and previous.status == "FAILED" else "MANUAL",
                user_id=principal.user_id, key=key, retry_of=previous.id if previous and previous.status == "FAILED" else None)
        if principal.delegation:
            from .process import add_process_event
            add_process_event(db, request_id=record.id, status=flow.status, actor=principal.role, principal=principal,
                note='Analizin yeniden çalıştırılması istendi.', action='DELEGATED_ANALYSIS', from_status=flow.status)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Bu talep için analiz zaten başlatıldı. Güncel kaydı açın.")
    return request_detail(db, record, flow, admin=principal.role == "NEEDS_ANALYST", role=principal.role)


def enqueue_extra_info(db, record, flow, principal):
    # The employee note and this run are committed together by execute_action.
    active = db.scalar(select(AnalysisRun).where(AnalysisRun.active_request_id == record.id))
    if active:
        db.execute(update(AnalysisRun).where(AnalysisRun.id == active.id, AnalysisRun.status.in_(ACTIVE)).values(
            status="FAILED", active_request_id=None, lease_token=None, lease_expires_at=None,
            completed_at=utc_now(), error_code="INPUT_CHANGED", error_message="Ek bilgi nedeniyle yeni analiz sürümü oluşturuldu."))
    db.flush()
    return enqueue(db, record, flow, trigger="EXTRA_INFO", user_id=principal.user_id)


def safe_failure(error):
    from .ai import AIResponseError, AIUnavailableError
    from .ai_errors import AIServiceError
    from .indexing import IndexNotReadyError
    if isinstance(error, IndexNotReadyError):
        code = "SOURCE_UNAVAILABLE"
    elif isinstance(error, (asyncio.TimeoutError, httpx.TimeoutException)):
        code = "TIMEOUT"
    elif isinstance(error, AIResponseError):
        code = "INVALID_RESPONSE"
    elif isinstance(error, AIServiceError):
        raw = error.payload["error_code"]
        code = "RATE_LIMITED" if raw in ("AI_RATE_LIMITED", "AI_DAILY_QUOTA_EXCEEDED") else "TIMEOUT" if raw == "AI_TIMEOUT" else "INVALID_RESPONSE" if raw == "AI_INVALID_RESPONSE" else "SERVICE_UNAVAILABLE"
    elif isinstance(error, httpx.HTTPStatusError):
        from .ai_errors import provider_error
        return safe_failure(provider_error(error, "analysis"))
    elif isinstance(error, (AIUnavailableError, httpx.HTTPError)):
        code = "SERVICE_UNAVAILABLE"
    else:
        code = "INTERNAL_FAILURE"
    messages = {"SOURCE_UNAVAILABLE": "Eğitim kaynakları veya arama dizini hazır değil.", "TIMEOUT": "Analiz hizmeti zamanında yanıt vermedi.",
        "INVALID_RESPONSE": "AI yanıtı doğrulanamadı.", "RATE_LIMITED": "Analiz hizmetinin kullanım sınırına ulaşıldı.",
        "SERVICE_UNAVAILABLE": "Analiz hizmetine şu anda ulaşılamıyor.", "INTERNAL_FAILURE": "Analiz işlemi tamamlanamadı; teknik inceleme gerekiyor."}
    return code, messages[code]


def fail_run(factory, run_id, token, code, message):
    with factory() as db:
        changed = db.execute(update(AnalysisRun).where(AnalysisRun.id == run_id, AnalysisRun.status == "PROCESSING",
            AnalysisRun.lease_token == token).values(status="FAILED", active_request_id=None, completed_at=utc_now(),
                error_code=code, error_message=message, lease_token=None, lease_expires_at=None))
        if changed.rowcount:
            run = db.get(AnalysisRun, run_id)
            analysis_event(db, run, f"Analiz sürümü {run.sequence} tamamlanamadı. " + message + " Talep kaydı korunuyor.", "ANALYSIS_FAILED")
            db.commit()


def recover_expired(factory):
    with factory() as db:
        rows = db.execute(select(AnalysisRun.id, AnalysisRun.lease_token).where(AnalysisRun.status == "PROCESSING",
            AnalysisRun.lease_expires_at <= utc_now())).all()
    for run_id, token in rows:
        # Re-check expiration in the failure transaction; a live worker may have renewed it.
        with factory() as db:
            changed = db.execute(update(AnalysisRun).where(AnalysisRun.id == run_id, AnalysisRun.status == "PROCESSING",
                AnalysisRun.lease_token == token, AnalysisRun.lease_expires_at <= utc_now()).values(
                    status="FAILED", active_request_id=None, lease_token=None, lease_expires_at=None,
                    completed_at=utc_now(), error_code="INTERRUPTED", error_message="Analiz kesintiye uğradı. Aynı talep yeniden denenebilir."))
            if changed.rowcount:
                analysis_event(db, db.get(AnalysisRun, run_id), "Analiz işlemi kesintiye uğradı. Talep korundu; yeniden denenebilir.", "ANALYSIS_FAILED")
                db.commit()


async def execute_run(factory, run_id, evaluator=None):
    from .services import compute_analysis
    token = uuid.uuid4().hex
    with factory() as db:
        changed = db.execute(update(AnalysisRun).where(AnalysisRun.id == run_id, AnalysisRun.status == "PENDING").values(
            status="PROCESSING", started_at=utc_now(), lease_token=token,
            lease_expires_at=utc_now() + timedelta(seconds=LEASE_SECONDS)))
        if not changed.rowcount:
            return False
        run = db.get(AnalysisRun, run_id)
        request_id, snapshot = run.request_id, json_loads(run.input_json, {})
        analysis_event(db, run, f"Analiz sürümü {run.sequence} başlatıldı.", "ANALYSIS_STARTED")
        db.commit()
        flow = db.get(RequestWorkflow, request_id)
        stale = flow.version != snapshot["request_version"]
    if stale:
        fail_run(factory, run_id, token, "INPUT_CHANGED", "Talep girdisi güncellendi. Güncel kayıt üzerinde yeniden deneyin.")
        return False

    async def compute():
        with factory() as db:
            text = input_text(db, snapshot, request_id)
            return await (evaluator or compute_analysis)(db, text)

    task = asyncio.create_task(compute())
    async def renew():
        while not task.done():
            await asyncio.sleep(LEASE_SECONDS / 3)
            with factory() as db:
                renewed = db.execute(update(AnalysisRun).where(AnalysisRun.id == run_id, AnalysisRun.status == "PROCESSING",
                    AnalysisRun.lease_token == token).values(lease_expires_at=utc_now() + timedelta(seconds=LEASE_SECONDS)))
                db.commit()
                if not renewed.rowcount:
                    task.cancel()
                    return
    heartbeat = asyncio.create_task(renew())
    try:
        result = await asyncio.wait_for(task, timeout=EXECUTION_TIMEOUT)
        if not isinstance(result, dict) or not isinstance(result.get("classification"), dict) or not isinstance(result.get("coverage"), dict):
            from .ai import AIResponseError
            raise AIResponseError("Invalid computed analysis")
        result["request_id"] = request_id
        from .learning import decision_support
        result["decision_support"] = decision_support(result, snapshot["original_request"])
        with factory() as db:
            run = db.get(AnalysisRun, run_id)
            if run.status != "PROCESSING" or run.lease_token != token:
                return False
            if run.lease_expires_at <= utc_now():
                db.rollback()
                fail_run(factory, run_id, token, "INTERRUPTED", "Analiz çalışma süresi kesintiye uğradı. Yeniden deneyebilirsiniz.")
                return False
            record, flow = db.get(RequestRecord, request_id), db.get(RequestWorkflow, request_id)
            # Reject publishing to a request changed while the model was working.
            claimed = db.execute(update(RequestWorkflow).where(RequestWorkflow.request_id == request_id,
                RequestWorkflow.version == snapshot["request_version"]).values(version=snapshot["request_version"] + 1,
                    updated_at=utc_now()))
            if not claimed.rowcount:
                db.rollback()
                fail_run(factory, run_id, token, "INPUT_CHANGED", "Analiz sırasında talep değişti. Güncel kayıt üzerinde yeniden deneyin.")
                return False
            completed = db.execute(update(AnalysisRun).where(AnalysisRun.id == run_id, AnalysisRun.status == "PROCESSING",
                AnalysisRun.lease_token == token, AnalysisRun.lease_expires_at > utc_now()).values(status="COMPLETED", active_request_id=None,
                    result_json=json_dumps(result), canonical_intent=str(result["classification"].get("canonical_intent", "")),
                    completed_at=utc_now(), lease_token=None, lease_expires_at=None))
            if not completed.rowcount:
                db.rollback()
                return False
            # Initial compatibility projection only; subsequent results never overwrite it.
            if not json_loads(flow.result_json, {}):
                flow.result_json = json_dumps(result)
                classification, coverage = result["classification"], result["coverage"]
                for field in ("category", "topic", "intent", "canonical_intent"):
                    setattr(record, field, str(classification.get(field, "")))
                record.coverage = coverage.get("status", "BELIRSIZ")
                record.ai_reason = coverage.get("reason", "")
                record.missing_topics_json = json_dumps(coverage.get("missing_topics", []))
                record.confidence = coverage.get("retrieval_score", 0)
                from .models import RequestMatch
                candidates = result.get("courses", []) + result.get("analysis", {}).get("supporting_courses", [])
                for candidate in candidates:
                    db.add(RequestMatch(request_id=request_id, course_id=candidate["course_id"],
                        score=candidate.get("score", 0), evidence_json=json_dumps(candidate.get("evidence", []))))
            analysis_event(db, run, f"Analiz sürümü {run.sequence} tamamlandı." + (" Ek bilgi sonrası analiz güncellendi." if run.trigger == "EXTRA_INFO" else ""), "ANALYSIS_COMPLETED")
            db.commit()
        return True
    except asyncio.CancelledError:
        fail_run(factory, run_id, token, "INTERRUPTED", "Analiz kesintiye uğradı. Talep korundu; yeniden deneyebilirsiniz.")
        if asyncio.current_task().cancelling():
            raise
        return False
    except Exception as error:
        code, message = safe_failure(error)
        # Log typed diagnostics without provider bodies, document text or secrets.
        logger.warning("Analysis failed: run=%s code=%s type=%s", run_id, code, type(error).__name__)
        fail_run(factory, run_id, token, code, message)
        return False
    finally:
        heartbeat.cancel()
        await asyncio.gather(heartbeat, return_exceptions=True)
        if not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)


async def worker(factory):
    async def recover_loop():
        while True:
            try:
                recover_expired(factory)
            except Exception as error:
                logger.error("Analysis recovery failed: %s", type(error).__name__)
            await asyncio.sleep(15)
    recovery = asyncio.create_task(recover_loop())
    try:
        while True:
            try:
                with factory() as db:
                    identifier = db.scalar(select(AnalysisRun.id).where(AnalysisRun.status == "PENDING").order_by(AnalysisRun.id).limit(1))
                if identifier:
                    await execute_run(factory, identifier)
                else:
                    await asyncio.sleep(1)
            except asyncio.CancelledError:
                raise
            except Exception as error:
                logger.error("Analysis worker iteration failed: %s", type(error).__name__)
                await asyncio.sleep(2)
    finally:
        recovery.cancel()
        await asyncio.gather(recovery, return_exceptions=True)
