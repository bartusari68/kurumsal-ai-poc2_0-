"""Workflow authority shared by mutations, detail projections and SQL work queues."""
from dataclasses import dataclass
from fastapi import HTTPException
from sqlalchemy import and_, case, select
from .models import PortalUser, RequestAssignment, RequestDecision, RequestReferral, RequestWorkflow
from .portal_auth import ROLES
from .utils import json_loads

STATUSES = {"IN_REVIEW": "İhtiyaç analizinde", "REFERRED": "Eğitim tasarımına yönlendirildi", "ACTION_PLANNED": "Çözüm planlandı", "NEEDS_INFO": "Ek bilgi bekleniyor", "RESOLVED": "Çözüme ulaştı", "LEGACY": "Önceki kayıt"}
DEPARTMENTS = {"TECHNICAL_DESIGN": "Teknik Eğitim Tasarım Şefliği", "ENGINEERING_DESIGN": "Mühendislik Eğitim Tasarım Şefliği"}
MANAGER_ROLES = ("NEEDS_ANALYST", *DEPARTMENTS)
STATES = {
    "IN_REVIEW": ("NEEDS_ANALYST", "REVIEW_REQUEST", "Analiz ekibi öneriyi değerlendirmeli ve uygun sonraki aşamaya ilerletmeli."),
    "LEGACY": ("NEEDS_ANALYST", "REVIEW_REQUEST", "Önceki kayıt analiz ekibi tarafından incelemeye alınmalı."),
    "REFERRED": ("@department", "DESIGN_REVIEW", "Sorumlu birim kapsamı değerlendirip çözüm planını oluşturmalı."),
    "ACTION_PLANNED": ("@department", "DELIVER_SOLUTION", "Planlanan çözümü uygulayın ve karşılanan ihtiyacı doğrulayın."),
    "NEEDS_INFO": ("EMPLOYEE", "PROVIDE_INFO", "Talep sahibi istenen bilgileri tamamlamalı."),
    "RESOLVED": (None, "COMPLETE", "Süreç tamamlandı; ek ihtiyaç doğarsa yeniden açılabilir."),
}
# Targets are intentionally unset: real institutional SLA values must be supplied.
# Keys: (status, responsible_scope) or (status, None). Values: target_seconds and,
# optionally, approaching_seconds. No invented deadline or warning threshold.
SLA_TARGETS = {}

# Primary work first; optional controls do not become the inbox's requested action.
INBOX_ACTION_ORDER = {
    'LEGACY': ('START_REVIEW', 'REVIEW_ADVANCE', 'REVIEW'),
    'IN_REVIEW': ('REVIEW_ADVANCE', 'REVIEW', 'SAVE_PLAN', 'REQUEST_INFO'),
    'REFERRED': ('REVIEW', 'SAVE_PLAN', 'REQUEST_INFO'),
    'ACTION_PLANNED': ('RESOLVE', 'SAVE_PLAN', 'REVIEW', 'REQUEST_INFO'),
    'NEEDS_INFO': ('PROVIDE_INFO',),
}


def sla_target(ctx):
    action = STATES.get(ctx['state'], STATES['LEGACY'])[1]
    for key in ((ctx['state'], action, ctx['scope']), (ctx['state'], action, None),
                (ctx['state'], ctx['scope']), (ctx['state'], None)):
        value = SLA_TARGETS.get(key)
        if value is not None:
            target = value.get('target_seconds') if isinstance(value, dict) else None
            if isinstance(target, bool) or not isinstance(target, (int, float)) or not 0 < target < float('inf'):
                return None
            warning = value.get('approaching_seconds')
            if warning is not None and (isinstance(warning, bool) or not isinstance(warning, (int, float)) or not 0 <= warning <= target):
                return None
            return value
    return None


@dataclass(frozen=True)
class Action:
    label: str
    sources: tuple
    roles: tuple
    target: str | None = None
    owner_only: bool = False
    fields: tuple = ("note",)
    min_note: int = 3
    routing_required: bool = False
    terminal: bool = False
    channel: str = "action"


ACTIONS = {
    "START_REVIEW": Action("Önceki kaydı incelemeye al", ("LEGACY",), ("NEEDS_ANALYST",), "IN_REVIEW"),
    "REQUEST_INFO": Action("Ek bilgi iste", ("IN_REVIEW", "REFERRED", "ACTION_PLANNED"), MANAGER_ROLES, "NEEDS_INFO", True),
    "PROVIDE_INFO": Action("Ek bilgiyi gönder", ("NEEDS_INFO",), ("EMPLOYEE",), "IN_REVIEW", True),
    "RETURN_REVIEW": Action("İhtiyaç analizine geri gönder", ("REFERRED", "ACTION_PLANNED", "NEEDS_INFO"), MANAGER_ROLES, "IN_REVIEW"),
    "REOPEN": Action("Yeniden inceleme iste", ("RESOLVED",), ("EMPLOYEE", *MANAGER_ROLES), "IN_REVIEW"),
    "RESOLVE": Action("Çözümün gerçekleştiğini bildir", ("ACTION_PLANNED",), ("EMPLOYEE", *MANAGER_ROLES), "RESOLVED", terminal=True),
    "REVIEW": Action("YZ değerlendirmesini kaydet", ("LEGACY", "IN_REVIEW", "REFERRED", "ACTION_PLANNED"), MANAGER_ROLES, fields=("outcome", "reason"), min_note=10, channel="review"),
    "REVIEW_ADVANCE": Action("Talebi değerlendir ve ilerlet", ("LEGACY", "IN_REVIEW", "REFERRED", "ACTION_PLANNED"), ("NEEDS_ANALYST",), fields=("outcome", "reason"), min_note=10, channel="review"),
    "REFER": Action("İlgili birime yönlendir", ("LEGACY", "IN_REVIEW", "REFERRED", "ACTION_PLANNED"), ("NEEDS_ANALYST",), "REFERRED", fields=("department", "analysis_summary", "training_need_confirmed"), min_note=10, routing_required=True, channel="referral"),
    "SAVE_PLAN": Action("Çözüm planını kaydet", ("IN_REVIEW", "REFERRED", "ACTION_PLANNED"), MANAGER_ROLES, "ACTION_PLANNED", True, ("summary", "responsible_unit"), 10, channel="plan"),
    "ASSIGN": Action("Kişisel atamayı güncelle", ("IN_REVIEW", "REFERRED", "ACTION_PLANNED"), MANAGER_ROLES, fields=("note",), channel="assignment"),
}


def owner_scope(status, department=None):
    scope = STATES.get(status, STATES["LEGACY"])[0]
    return department or "NEEDS_ANALYST" if scope == "@department" else scope


def owner_expression():
    """SQL equivalent generated from the same state configuration; no list-only rules."""
    dept = select(RequestReferral.department).where(RequestReferral.request_id == RequestWorkflow.request_id,
        RequestReferral.active.is_(True), RequestReferral.training_need_confirmed.is_(True)).correlate(RequestWorkflow).scalar_subquery()
    from sqlalchemy import func
    return case(*[(RequestWorkflow.status == state, func.coalesce(dept, "NEEDS_ANALYST") if scope == "@department" else scope)
                  for state, (scope, _, _) in STATES.items()], else_="NEEDS_ANALYST")


def context(db, record, flow, *, include_review=True):
    state = flow.status if flow else "LEGACY"
    referral = db.get(RequestReferral, record.id)
    department = referral.department if referral and referral.active and referral.training_need_confirmed else None
    scope = owner_scope(state, department)
    assignment = db.get(RequestAssignment, record.id)
    user = db.get(PortalUser, assignment.assignee_id) if assignment and assignment.assignee_id else None
    valid_user = user and user.active and user.role == scope and assignment.responsible_scope == scope
    from .analysis_pipeline import current_result, review_ready, decision_is_current
    result = current_result(db, record, flow)
    latest = db.scalar(select(RequestDecision).where(RequestDecision.request_id == record.id).order_by(RequestDecision.id.desc()).limit(1)) if include_review else None
    ready = review_ready(db, record, flow) if include_review else True
    return {"state": state, "scope": scope, "department": department,
            "assignee": {"id": user.id, "display_name": user.display_name} if valid_user else None,
            "critical": result.get("classification", {}).get("risk_level") == "KRITIK",
            "analysis_review_ready": ready,
            "reviewed": bool(ready and latest and latest.outcome in ("APPROVED", "MODIFIED") and decision_is_current(db, latest, record, flow))}


def permitted(code, ctx, role):
    rule = ACTIONS.get(code)
    if not rule or ctx["state"] not in rule.sources or role not in rule.roles:
        return False
    if role in DEPARTMENTS and ctx["department"] != role:
        return False
    if code in ("REVIEW", "REVIEW_ADVANCE") and not ctx.get("analysis_review_ready", True):
        return False
    if rule.owner_only and role != ctx["scope"]:
        return False
    if code == "RESOLVE" and (role == "EMPLOYEE" and ctx["critical"] or role in MANAGER_ROLES and role != ctx["scope"]):
        return False
    if code == "SAVE_PLAN" and ctx["state"] == "IN_REVIEW" and not ctx["reviewed"]:
        return False
    if code == "ASSIGN" and role not in ("NEEDS_ANALYST", ctx["scope"]):
        return False
    return True


def authorize(db, record, flow, role, code, expected_version):
    if expected_version != (flow.version if flow else 0):
        raise HTTPException(409, "Talep başka bir işlemde güncellendi. Yeniden açın.")
    ctx = context(db, record, flow)
    if not permitted(code, ctx, role):
        raise HTTPException(422, "Bu aşamada bu işlem için yetkiniz yok. Talebin güncel işlem alanını kullanın.")
    return ctx


def available_actions(ctx, role):
    return [{"code": code, "label": rule.label, "target": rule.target, "required_fields": list(rule.fields),
             "note_required": rule.min_note > 0, "min_note_length": rule.min_note,
             "routing_required": rule.routing_required, "terminal": rule.terminal,
             "audit_event": code, "channel": rule.channel}
            for code, rule in ACTIONS.items() if permitted(code, ctx, role)]


def review_target(*, outcome, training, critical, support_action, course_id, missing):
    """Existing human review business rules, now owned by the transition policy."""
    if outcome == "REJECTED" or not training or critical or support_action == "URGENT_REVIEW" or (outcome == "APPROVED" and support_action == "CLARIFY"):
        return "IN_REVIEW"
    if course_id is not None and not missing and (outcome == "MODIFIED" or support_action == "USE_COURSE"):
        return "ACTION_PLANNED"
    return "REFERRED"


def status_action(state, target):
    """Compatibility adapter; old status APIs cannot evade the action policy."""
    mapping = {"RESOLVED": "RESOLVE", "NEEDS_INFO": "REQUEST_INFO", "ACTION_PLANNED": "SAVE_PLAN"}
    if target == "IN_REVIEW":
        return {"LEGACY": "START_REVIEW", "NEEDS_INFO": "PROVIDE_INFO", "RESOLVED": "REOPEN"}.get(state, "RETURN_REVIEW")
    return mapping.get(target)


def queue_views(role, has_assignment=False):
    views = [{"id": "", "label": "Tüm işler"}, {"id": "actionable", "label": "Aksiyon bekleyenler"}]
    if role in MANAGER_ROLES:
        views.append({"id": "unit", "label": "Birimimin işleri"})
    if has_assignment:
        views.append({"id": "assigned", "label": "Bana atananlar"})
    return views + [{"id": key, "label": label} for key, label in (("info", "Ek bilgi bekleyenler"), ("planned", "Çözüm planlananlar"), ("completed", "Tamamlananlar"))]


def queue_condition(view, role, user_id):
    owner = owner_expression()
    assignment = select(RequestAssignment.request_id).join(PortalUser, PortalUser.id == RequestAssignment.assignee_id).where(
        RequestAssignment.assignee_id == user_id, PortalUser.active.is_(True), PortalUser.role == owner,
        RequestAssignment.responsible_scope == owner).correlate(RequestWorkflow).scalar_subquery()
    conditions = {"": True, "actionable": owner == role, "unit": owner == role,
                  "assigned": RequestWorkflow.request_id.in_(assignment),
                  "info": RequestWorkflow.status == "NEEDS_INFO", "planned": RequestWorkflow.status == "ACTION_PLANNED",
                  "completed": RequestWorkflow.status == "RESOLVED"}
    if view not in conditions:
        raise HTTPException(422, "Geçersiz iş kuyruğu filtresi.")
    return conditions[view]
