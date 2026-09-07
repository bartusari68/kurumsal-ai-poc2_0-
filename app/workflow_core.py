"""Small transaction services for ownership, plans and explicit workflow actions."""
from .time_policy import utc_now, as_utc, utc_stamp
from datetime import datetime, time
from fastapi import HTTPException
from sqlalchemy import select, update
from .models import (PortalUser, RequestAssignment, RequestEvent, RequestEventAction,
                     RequestReferral, RequestSolutionPlan, RequestWorkflow, UserOrganization)
from . import workflow_policy as policy
from .utils import json_loads, json_dumps


def organization_payload(db, user_id):
    row = db.get(UserOrganization, user_id) if user_id else None
    fields = ("organization", "directorate", "unit", "chiefdom", "manager_user_id")
    data = {key: getattr(row, key, None) for key in fields}
    labels = [data[key] for key in fields[:-1] if data[key]]
    return {**data, "name": data["organization"], "known": any(data.values()),
            "label": " / ".join(labels) if labels else "Organizasyon bilgisi tanımlanmamış"}


def plan_payload(db, plan):
    if not plan:
        return None
    from .workflow import stamp
    author = db.get(PortalUser, plan.created_by)
    user = db.get(PortalUser, plan.assignee_id) if plan.assignee_id else None
    return {"summary": plan.summary, "responsible_unit": plan.responsible_unit,
            "responsible_unit_label": policy.DEPARTMENTS.get(plan.responsible_unit, "İhtiyaç Analizi Ekibi"),
            "assignee": {"id": user.id, "display_name": user.display_name} if user else None,
            "target_date": plan.target_date.date().isoformat() if plan.target_date else None, "state": plan.state,
            "created_by": {"id": plan.created_by, "display_name": author.display_name if author else "Kişi bilgisi mevcut değil"},
            "created_at": stamp(plan.created_at), "updated_at": stamp(plan.updated_at)}


def aging(db, record, flow, ctx):
    now = utc_now()
    events = db.execute(select(RequestEvent.status, RequestEvent.created_at).where(RequestEvent.request_id == record.id).order_by(RequestEvent.created_at, RequestEvent.id)).all()
    state, stage_at = "IN_REVIEW" if flow else "LEGACY", record.created_at
    for event in events:
        if event.status != state:
            state, stage_at = event.status, event.created_at
    # Older data may have a status without a corresponding event: do not invent its start.
    known = state == ctx["state"]
    age = lambda value: max(0, int((now - as_utc(value)).total_seconds())) if value else None
    stage_seconds = age(stage_at) if known else None
    last_at = max(as_utc(value) for value in [record.created_at] + [event.created_at for event in events] + ([flow.updated_at] if flow else []))
    target = policy.sla_target(ctx)
    sla = None
    if target and target.get("target_seconds", 0) > 0 and stage_seconds is not None and ctx["state"] != "RESOLVED":
        remaining = target["target_seconds"] - stage_seconds
        warning = target.get("approaching_seconds")
        sla = {"target_seconds": target["target_seconds"], "remaining_seconds": remaining,
               "state": "overdue" if remaining < 0 else "approaching" if warning is not None and remaining <= warning else "normal"}
    return {"current_stage_seconds": stage_seconds, "last_action_seconds": age(last_at),
            "created_seconds": age(record.created_at), "stage_started_at": utc_stamp(stage_at) if known else None,
            "last_action_at": utc_stamp(last_at), "sla": sla}


def projection(db, record, flow, role):
    ctx = policy.context(db, record, flow)
    actions = policy.available_actions(ctx, role)
    candidates = []
    if any(item["code"] in ("ASSIGN", "SAVE_PLAN") for item in actions):
        candidates = [{"id": user.id, "display_name": user.display_name} for user in db.scalars(
            select(PortalUser).where(PortalUser.active.is_(True), PortalUser.role == ctx["scope"]).order_by(PortalUser.display_name))]
    return {"current_state": ctx["state"], "responsible_scope": ctx["scope"], "assignee": ctx["assignee"],
            "available_actions": actions, "assignment_options": candidates,
            "plan": plan_payload(db, db.get(RequestSolutionPlan, record.id)), "aging": aging(db, record, flow, ctx)}


def checked_user(db, user_id, scope):
    if user_id is None:
        return None
    user = db.get(PortalUser, user_id)
    if not user or not user.active or user.role != scope:
        raise HTTPException(422, "Atanan kişi sorumlu birimin aktif kullanıcılarından biri olmalıdır.")
    return user


def lock_flow(db, record, flow, expected_version, **values):
    if not flow:
        # Unique primary key protects concurrent legacy activation; caller's transaction rolls back on conflict.
        flow = RequestWorkflow(request_id=record.id, owner_hash="", status="IN_REVIEW", result_json="{}", version=0)
        db.add(flow)
        from sqlalchemy.exc import IntegrityError
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            raise HTTPException(409, "Talep başka bir işlemde güncellendi. Yeniden açın.")
    changed = db.execute(update(RequestWorkflow).where(RequestWorkflow.request_id == record.id,
        RequestWorkflow.version == expected_version).values(version=expected_version + 1, updated_at=utc_now(), **values))
    if changed.rowcount != 1:
        db.rollback()
        raise HTTPException(409, "Talep başka bir işlemde güncellendi. Yeniden açın.")
    return flow


def write_plan(db, record, flow, principal, *, summary, scope, assignee_id=None, target_date=None, from_status=None):
    """Called inside the same version-locked transaction as the review/action."""
    from .process import add_process_event
    plan = db.get(RequestSolutionPlan, record.id)
    before = plan_payload(db, plan)
    if not plan:
        plan = RequestSolutionPlan(request_id=record.id, created_by=principal.user_id, created_at=utc_now())
        db.add(plan)
    plan.summary, plan.responsible_unit, plan.assignee_id = summary, scope, assignee_id
    plan.target_date = datetime.combine(target_date, time.min) if target_date else None
    plan.state, plan.updated_at = "planned", utc_now()
    add_process_event(db, request_id=record.id, status="ACTION_PLANNED", actor=principal.role, principal=principal,
        note=("Çözüm planı güncellendi: " if before else "Çözüm planı oluşturuldu: ") + summary,
        action="PLAN_UPDATED" if before else "PLAN_CREATED", from_status=from_status or flow.status,
        details={"before": before, "after": plan_payload(db, plan)})
    return plan


def transition_effects(db, record, old_status, target):
    if target == "IN_REVIEW":
        referral = db.get(RequestReferral, record.id)
        if referral:
            referral.active = False
    if target != old_status:
        assignment = db.get(RequestAssignment, record.id)
        if assignment:
            assignment.assignee_id = None
            assignment.updated_at = utc_now()
        plan = db.get(RequestSolutionPlan, record.id)
        if plan and target in ("IN_REVIEW", "RESOLVED"):
            plan.state = "completed" if target == "RESOLVED" else "superseded"
            plan.updated_at = utc_now()


def execute_action(db, record, flow, principal, payload):
    from .workflow import owned_request, request_detail
    from .process import add_process_event
    from sqlalchemy.exc import IntegrityError
    values = payload.model_dump() if hasattr(payload, "model_dump") else dict(payload)
    code, expected = values.get("action"), values.get("expected_version")
    owned_request(db, record.id, principal.token_hash, admin=principal.role != "EMPLOYEE", role=principal.role)
    ctx = policy.authorize(db, record, flow, principal.role, code, expected)
    rule = policy.ACTIONS[code]
    if rule.channel not in ("action", "plan", "assignment"):
        raise HTTPException(422, "Bu işlem için değerlendirme veya yönlendirme formunu kullanın.")
    note = str(values.get("summary") if code == "SAVE_PLAN" else values.get("note") or "").strip()
    if not rule.min_note <= len(note) <= 3000:
        raise HTTPException(422, f"Açıklama en az {rule.min_note}, en çok 3000 karakter olmalıdır.")
    target = rule.target or ctx["state"]
    scope = ctx["scope"]
    user_id = values.get("assignee_id")
    assignee_user = None
    if code in ("ASSIGN", "SAVE_PLAN"):
        assignee_user = checked_user(db, user_id, scope)
    if code == "SAVE_PLAN" and values.get("responsible_unit") != scope:
        raise HTTPException(422, "Çözüm planı talebin mevcut sorumlu birimine ait olmalıdır.")
    try:
        previous_plan = plan_payload(db, db.get(RequestSolutionPlan, record.id))
        flow = lock_flow(db, record, flow, expected, status=target, public_note=note)
        details = {}
        if code == "SAVE_PLAN":
            write_plan(db, record, flow, principal, summary=note, scope=scope, assignee_id=user_id, target_date=values.get("target_date"), from_status=ctx["state"])
        transition_effects(db, record, ctx["state"], target)
        if code in ("ASSIGN", "SAVE_PLAN"):
            assignment = db.get(RequestAssignment, record.id)
            if not assignment:
                assignment = RequestAssignment(request_id=record.id)
                db.add(assignment)
            details = {"previous_assignee": ctx["assignee"], "assignee_id": user_id, "responsible_scope": scope}
            assignment.assignee_id, assignment.responsible_scope = user_id, scope
            assignment.assigned_by, assignment.updated_at = principal.user_id, utc_now()
            if code == "ASSIGN":
                plan = db.get(RequestSolutionPlan, record.id)
                if plan and plan.state == "planned" and plan.responsible_unit == scope:
                    before = plan_payload(db, plan)
                    plan.assignee_id, plan.updated_at = user_id, utc_now()
                    details["plan"] = {"before": before, "after": plan_payload(db, plan)}
        if previous_plan and code not in ("SAVE_PLAN", "ASSIGN"):
            details["plan"] = {"before": previous_plan, "after": plan_payload(db, db.get(RequestSolutionPlan, record.id))}
        action_note = rule.label + ": " + note
        if code == "ASSIGN":
            action_note += " Atanan kişi: " + (assignee_user.display_name if assignee_user else "Kişisel atama kaldırıldı; birim iş kuyruğu sorumlu.")
        add_process_event(db, request_id=record.id, status=target, actor=principal.role, principal=principal,
            note=action_note, action=code, from_status=ctx["state"], details=details)
        if code == "PROVIDE_INFO":
            from .analysis_pipeline import enqueue_extra_info
            db.flush()
            enqueue_extra_info(db, record, flow, principal)
        db.commit()
        db.refresh(flow)
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Talep başka bir işlemde güncellendi. Yeniden açın.")
    except Exception:
        db.rollback()
        raise
    return request_detail(db, record, flow, admin=principal.role == "NEEDS_ANALYST", role=principal.role)
