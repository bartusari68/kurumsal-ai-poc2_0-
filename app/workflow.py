"""Employee projections, persistent request tracking and explicit resolution."""
from .time_policy import utc_now, as_utc, utc_stamp
from datetime import datetime
from fastapi import HTTPException
from sqlalchemy import func, or_, select, update
from .models import Course, RequestEvent, RequestRecord, RequestWorkflow, RequestReferral
from .portal_auth import ROLES, MANAGERS
from .indexing import source_path
from .utils import compact_text, json_dumps, json_loads
from .process import action_projection, add_process_event, creator_identity, process_summary, resolve_routing

from .workflow_policy import STATUSES, DEPARTMENTS
from . import workflow_policy as policy



def audience_scope(owner_hash, admin, role):
    if not admin:
        return RequestWorkflow.owner_hash == owner_hash
    if role == "NEEDS_ANALYST":
        return True
    if role not in DEPARTMENTS:
        raise HTTPException(403, "Bu alan için yetkiniz yok.")
    return RequestRecord.id.in_(select(RequestReferral.request_id).where(
        RequestReferral.department == role, RequestReferral.active.is_(True),
        RequestReferral.training_need_confirmed.is_(True)))


def stamp(value):
    return utc_stamp(value)


def record_analysis(db, record, result, owner_hash):
    from .learning import decision_support
    result["decision_support"] = decision_support(result, record.text)
    db.add(RequestWorkflow(request_id=record.id, owner_hash=owner_hash, status="IN_REVIEW", result_json=json_dumps(result)))
    db.add(RequestEvent(request_id=record.id, status="IN_REVIEW", actor="SYSTEM", note="Talep alındı ve ilk değerlendirme hazırlandı. Henüz çözülmüş sayılmaz."))


def public_result(result):
    from .learning import decision_support
    classification = result.get("classification", {})
    coverage = result.get("coverage", {})
    support = decision_support(result)
    return {"request_id": result.get("request_id"), "classification": {key: classification.get(key) for key in
            ("category", "subcategory", "subcategory_id", "topic", "need_type")},
            "decision_support": {key: support.get(key) for key in ("action", "action_label", "fit_percent", "human_confirmation_required")},
            "urgent_review": classification.get("risk_level") == "KRITIK",
            "coverage": {"status": coverage.get("status"), "reason": coverage.get("reason", ""), "missing_topics": coverage.get("missing_topics", []),
                         "fit_percent": coverage.get("fit_percent"), "needs_new_course": coverage.get("needs_new_course"),
                         "next_action": coverage.get("next_action")},
            "courses": [{key: course.get(key) for key in ("course_id", "course_name", "fit", "source_available")} for course in result.get("courses", [])]}


def request_detail(db, record, workflow, *, admin=False, role="EMPLOYEE"):
    from .analysis_pipeline import current_result, analysis_projection
    result = current_result(db, record, workflow)
    if not result:
        from .analysis_pipeline import latest_run
        pending_analysis = latest_run(db, record.id) is not None
        result = {"request_id": record.id, "classification": {"category": record.category, "topic": record.topic},
                  "coverage": {"status": record.coverage, "reason": "Henüz başarılı bir AI analizi bulunmuyor. Talebiniz kayıtlıdır." if pending_analysis else "Bu kayıt önceki analiz sürümüne aittir; yeni uyum yüzdesi hesaplanmamıştır."}, "courses": []}
    for course in result.get("courses", []):
        source = db.get(Course, course["course_id"])
        course["source_available"] = bool(source and source_path(source.pdf_path).is_file())
    payload = result if admin else public_result(result)
    referral = db.get(RequestReferral, record.id)
    payload["referral"] = {"department": referral.department, "department_label": DEPARTMENTS[referral.department],
                           "analysis_summary": referral.analysis_summary, "completed_at": stamp(referral.completed_at),
                           "active": referral.active, "training_need_confirmed": referral.training_need_confirmed} if referral else None
    from .learning import can_review, decision_history, decision_support, review_options, prior_case_support
    ctx = policy.context(db, record, workflow)
    review_allowed = policy.permitted("REVIEW", ctx, role)
    payload["permissions"] = {"can_refer": policy.permitted("REVIEW_ADVANCE", ctx, role), "can_manage": role in MANAGERS, "can_review": review_allowed}
    if role in MANAGERS:
        payload["decisions"] = decision_history(db, record.id, include_audit=role == "NEEDS_ANALYST")
    if review_allowed:
        payload["decision_support"] = decision_support(result, record.text)
        payload["decisions"] = decision_history(db, record.id, include_audit=role == "NEEDS_ANALYST")
        payload["review_options"] = review_options(db)
        if role == "NEEDS_ANALYST":
            payload["decision_support"]["prior_cases"] = prior_case_support(db, record.canonical_intent, exclude_request_id=record.id)
    payload["urgent_review"] = result.get("classification", {}).get("risk_level") == "KRITIK"
    events = db.scalars(select(RequestEvent).where(RequestEvent.request_id == record.id).order_by(RequestEvent.id)).all()
    payload.update(text=record.text, created_at=stamp(record.created_at), updated_at=stamp(workflow.updated_at if workflow else record.created_at),
                   status=workflow.status if workflow else "LEGACY", status_label=STATUSES[workflow.status if workflow else "LEGACY"],
                   public_note=workflow.public_note if workflow else "", version=workflow.version if workflow else 0,
                   events=[{"status": event.status, "label": STATUSES[event.status], "actor": event.actor, "note": event.note, "at": stamp(event.created_at)} for event in events])
    payload["analysis_state"] = analysis_projection(db, record, workflow, role)
    payload["process"] = process_summary(db, record, workflow, manager=role in MANAGERS, role=role)
    from .development import request_links
    payload['development'] = request_links(db, record, workflow, role)
    if review_allowed:
        payload["routing"] = resolve_routing(db, record, workflow)
        payload["permissions"]["can_review_and_advance"] = policy.permitted("REVIEW_ADVANCE", ctx, role)
    return payload


def owned_request(db, request_id, owner_hash, admin=False, role="EMPLOYEE"):
    record = db.scalar(select(RequestRecord).outerjoin(RequestWorkflow).where(
        RequestRecord.id == request_id, audience_scope(owner_hash, admin, role)))
    flow = db.get(RequestWorkflow, request_id)
    if not record or (not admin and (not flow or flow.owner_hash != owner_hash)):
        raise HTTPException(404, "Talep bulunamadı.")
    return record, flow


def request_list(db, owner_hash, *, admin=False, role="EMPLOYEE", status=None, search="", offset=0, limit=20, sort="newest", view="", user_id=None):
    base = select(RequestRecord, RequestWorkflow).outerjoin(RequestWorkflow, RequestWorkflow.request_id == RequestRecord.id)
    scope = audience_scope(owner_hash, admin, role)
    base = base.where(scope)
    # Counters refer to this audience, not the filtered page.
    summary = {key: 0 for key in STATUSES}
    counts = select(func.coalesce(RequestWorkflow.status, "LEGACY"), func.count(RequestRecord.id)).select_from(RequestRecord).outerjoin(RequestWorkflow)
    counts = counts.where(scope)
    for state, count in db.execute(counts.group_by(RequestWorkflow.status)):
        summary[state] = count
    actionable_count = db.scalar(select(func.count(RequestRecord.id)).select_from(RequestRecord).outerjoin(RequestWorkflow).where(
        scope, policy.queue_condition("actionable", role, user_id))) or 0
    if status and status not in STATUSES:
        raise HTTPException(422, "Geçersiz durum filtresi.")
    if status:
        base = base.where(RequestWorkflow.status == status if status != "LEGACY" else RequestWorkflow.request_id.is_(None))
    base = base.where(policy.queue_condition(view, role, user_id))
    if search:
        # LIKE wildcards are user text, not query operators.
        term = search.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        base = base.where(or_(RequestRecord.text.ilike("%" + term + "%", escape="\\"),
                              RequestRecord.topic.ilike("%" + term + "%", escape="\\")))
    total = db.scalar(select(func.count()).select_from(base.subquery())) or 0
    ordering = {"newest": RequestRecord.id.desc(), "oldest": RequestRecord.id.asc(),
                "updated": func.coalesce(RequestWorkflow.updated_at, RequestRecord.created_at).desc()}
    if sort not in ordering:
        raise HTTPException(422, "Geçersiz sıralama seçimi.")
    items = []
    for record, flow in db.execute(base.order_by(ordering[sort], RequestRecord.id.desc()).offset(offset).limit(limit)):
        from .analysis_pipeline import current_result
        result = current_result(db, record, flow)
        classification = result.get("classification", {})
        referral = db.get(RequestReferral, record.id)
        state = flow.status if flow else "LEGACY"
        active_department = referral.department if referral and referral.active and referral.training_need_confirmed else None
        creator = creator_identity(db, flow.owner_hash) if flow and state == "NEEDS_INFO" else None
        items.append({"request_id": record.id, "text": compact_text(record.text, 180), "category": record.category,
                      "subcategory": classification.get("subcategory", "Önceki sınıflandırma"), "topic": classification.get("topic") or record.topic,
                      "status": flow.status if flow else "LEGACY", "status_label": STATUSES[flow.status if flow else "LEGACY"],
                      "fit_percent": result.get("coverage", {}).get("fit_percent"), "created_at": stamp(record.created_at),
                      "department_label": DEPARTMENTS[active_department] if active_department else "İhtiyaç analizi",
                      **action_projection(state, active_department=active_department, creator=creator),
                      **_queue_projection(db, record, flow, role)})
    from .models import RequestAssignment
    has_assignment = db.scalar(select(RequestRecord.id).outerjoin(RequestWorkflow).where(scope,
        policy.queue_condition("assigned", role, user_id)).limit(1)) is not None
    return {"queue_views": policy.queue_views(role, has_assignment), "items": items, "total": total, "offset": offset, "limit": limit,
            "summary": {**summary, "total": sum(summary.values()), "actionable": actionable_count}}


def change_status(db, record, flow, *, owner_hash, admin, target, note, expected_version, role="EMPLOYEE", principal=None):
    """Backward compatible status adapter; all mutations use the action engine."""
    from .workflow_core import execute_action
    from .portal_auth import Principal
    if not principal:
        identity = creator_identity(db, owner_hash)
        if not identity["known"] or identity["role"] != role:
            raise HTTPException(403, "Geçerli kullanıcı oturumu gerekir.")
        principal = Principal(identity["id"], "", identity["display_name"], role)
    code = policy.status_action(flow.status if flow else "LEGACY", target)
    if code == "PROVIDE_INFO" and role != "EMPLOYEE":
        code = "RETURN_REVIEW"
    values = {"action": code, "note": note, "expected_version": expected_version}
    if code == "SAVE_PLAN":
        values.update(summary=note, responsible_unit=policy.context(db, record, flow)["scope"])
    return execute_action(db, record, flow, principal, values)


def refer_request(db, record, flow, principal, department, analysis_summary, training_need_confirmed, expected_version):
    if principal.role != "NEEDS_ANALYST":
        raise HTTPException(403, "Yalnızca ihtiyaç analizi yöneticisi yönlendirebilir.")
    if department not in DEPARTMENTS or not training_need_confirmed or len(analysis_summary.strip()) < 10:
        raise HTTPException(422, "Eğitim ihtiyacını onaylayın, analiz sonucunu yazın ve ilgili şefliği seçin.")
    owned_request(db, record.id, principal.token_hash, admin=True, role=principal.role)
    ctx = policy.authorize(db, record, flow, principal.role, "REFER", expected_version)
    from .workflow_core import lock_flow, transition_effects, plan_payload
    from .models import RequestSolutionPlan
    previous_plan = plan_payload(db, db.get(RequestSolutionPlan, record.id))
    note = analysis_summary.strip()
    flow = lock_flow(db, record, flow, expected_version, status="REFERRED", public_note=note)
    transition_effects(db, record, ctx["state"], "REFERRED")
    from .models import RequestAssignment, RequestSolutionPlan
    assignment = db.get(RequestAssignment, record.id)
    if assignment and assignment.responsible_scope != department:
        assignment.assignee_id = None
    plan = db.get(RequestSolutionPlan, record.id)
    if plan:
        plan.state = "superseded"
    referral = db.get(RequestReferral, record.id)
    if not referral:
        referral = RequestReferral(request_id=record.id)
        db.add(referral)
    referral.department, referral.analysis_summary = department, note
    referral.training_need_confirmed, referral.active = True, True
    referral.analyst_id, referral.completed_at = principal.user_id, utc_now()
    add_process_event(db, request_id=record.id, status="REFERRED", actor=principal.role, principal=principal,
                      note=DEPARTMENTS[department] + " birimine yönlendirildi. Analiz: " + note,
                      action="REFER", from_status=ctx["state"], details={"department": department, "plan": {"before": previous_plan, "after": plan_payload(db, plan)}})
    db.commit()
    db.refresh(flow)
    return request_detail(db, record, flow, admin=True, role=principal.role)


def _queue_projection(db, record, flow, role):
    from .workflow_core import aging
    ctx = policy.context(db, record, flow, include_review=False)
    last = db.execute(select(RequestEvent.note, RequestEvent.created_at).where(RequestEvent.request_id == record.id).order_by(RequestEvent.created_at.desc(), RequestEvent.id.desc()).limit(1)).first()
    from .models import RequestDecision
    from .learning import OUTCOMES
    decision = db.execute(select(RequestDecision.outcome, RequestDecision.created_at).where(RequestDecision.request_id == record.id).order_by(RequestDecision.id.desc()).limit(1)).first()
    last_action = {"note": last.note, "at": stamp(last.created_at)} if last else None
    if decision and (not last or decision.created_at >= last.created_at):
        last_action = {"note": "İnsan değerlendirmesi: " + OUTCOMES[decision.outcome], "at": stamp(decision.created_at)}
    return {"current_stage": STATUSES[ctx["state"]], "responsible_scope": ctx["scope"],
            "assignee": ctx["assignee"], "aging": aging(db, record, flow, ctx),
            "last_action": last_action}
