"""Honest process projections and operational routing from persisted evidence."""
from sqlalchemy import select

from .models import (PortalUser, RequestDecision, RequestEvent, RequestEventIdentity,
                     RequestReferral)
from .portal_auth import ROLES


def creator_identity(db, owner_hash):
    identifier = str(owner_hash or "").removeprefix("user:")
    user = db.get(PortalUser, int(identifier)) if str(owner_hash).startswith("user:") and identifier.isdecimal() else None
    return {"id": user.id if user else None, "display_name": user.display_name if user else "Oluşturan bilgisi kayıtlı değil",
            "role": user.role if user else "EMPLOYEE", "known": user is not None}


def add_process_event(db, *, request_id, status, actor, note, principal=None, owner_hash=None, action=None, from_status=None, details=None):
    details = dict(details or {})
    if principal and principal.delegation:
        details['delegation'] = dict(principal.delegation)
        note += ' ' + principal.display_name + ', ' + principal.delegation['delegator_name'] + ' adına vekâleten işlem yaptı.'
    entry = RequestEvent(request_id=request_id, status=status, actor=actor, note=note)
    db.add(entry)
    identity = ({"id": principal.user_id, "display_name": principal.display_name, "role": principal.role, "known": True}
                if principal else creator_identity(db, owner_hash) if owner_hash else None)
    if identity and identity["known"]:
        db.add(RequestEventIdentity(event=entry, user_id=identity["id"], display_name=identity["display_name"], role=identity["role"]))
    if action:
        from .models import RequestEventAction
        from .utils import json_dumps
        db.add(RequestEventAction(event=entry, action=action, from_status=from_status or status,
                                  to_status=status, details_json=json_dumps(details or {})))
        from .operations import capture_event
        capture_event(db, entry, action, details)
    return entry


def resolve_routing(db, record, flow, *, category=None, department=None):
    """A configured subject rule proposes work ownership, never employee organization."""
    from .learning import department_suggestion, human_routing_department
    from .workflow import DEPARTMENTS
    from .utils import json_loads
    from .analysis_pipeline import current_result, decision_is_current
    result = current_result(db, record, flow)
    category = category or result.get("classification", {}).get("subcategory_id")
    source, reason, target = None, "Bu konu için tanımlı hedef bulunmuyor. Sorumlu tasarım birimini bir kez seçin.", None
    if department in DEPARTMENTS:
        target, source, reason = department, "human_selection", "Bu işlemde seçilen sorumlu birim."
    else:
        latest = db.scalar(select(RequestDecision).where(RequestDecision.request_id == record.id).order_by(RequestDecision.id.desc()).limit(1))
        referral = db.get(RequestReferral, record.id)
        if latest and not decision_is_current(db, latest, record, flow):
            latest = None
        latest_department = human_routing_department(latest) if latest else None
        if (latest and latest.outcome != "REJECTED" and latest.training_need_confirmed
                and latest_department in DEPARTMENTS and latest.actual_subcategory_id == category
                and not (referral and referral.active and referral.completed_at >= latest.created_at)):
            target, source, reason = latest_department, "human_decision", "Bu talep için kaydedilmiş son insan kararındaki sorumlu birim."
        # A changed human category gets its own rule, not a stale earlier destination.
        original_category = result.get("classification", {}).get("subcategory_id")
        if not target and referral and referral.active and category == original_category:
            target, source, reason = referral.department, "active_referral", "Talebin halen atandığı sorumlu birim."
        if not target:
            suggested = department_suggestion({"subcategory_id": category})
            target, source, reason = suggested["id"], "category_rule" if suggested["id"] else None, suggested["reason"]
    return {"department": target, "department_label": DEPARTMENTS.get(target), "resolved": target is not None,
            "source": source, "reason": reason, "requires_selection": target is None,
            "options": [{"id": key, "label": label} for key, label in DEPARTMENTS.items()]}


def action_projection(status, *, active_department=None, creator=None):
    """Shared list/detail ownership rules; no database, timeline or audit reads."""
    from .workflow_policy import owner_scope, STATES, DEPARTMENTS
    owner = owner_scope(status, active_department)
    _, next_code, next_label = STATES.get(status, STATES["LEGACY"])
    label = DEPARTMENTS.get(owner, "İhtiyaç Analizi Ekibi" if owner == "NEEDS_ANALYST" else ROLES.get(owner, "Tamamlandı"))
    return {"current_owner": {"role": owner, "label": label}, "next_action": {"code": next_code, "label": next_label}}


def process_summary(db, record, flow, *, manager=False, role="EMPLOYEE"):
    from .learning import OUTCOMES
    from .workflow import STATUSES, stamp
    creator = creator_identity(db, flow.owner_hash if flow else None)
    status = flow.status if flow else "LEGACY"
    referral = db.get(RequestReferral, record.id)
    active_department = referral.department if referral and referral.active and referral.training_need_confirmed else None
    timeline = [{"id": "created", "kind": "created", "label": "Talep oluşturuldu", "status": "IN_REVIEW",
                 "actor": creator, "note": "Talep sisteme kaydedildi.", "at": stamp(record.created_at)}]
    events = db.execute(select(RequestEvent, RequestEventIdentity).outerjoin(RequestEventIdentity).where(
        RequestEvent.request_id == record.id).order_by(RequestEvent.created_at, RequestEvent.id)).all()
    from .models import RequestEventAction
    from .utils import json_loads
    action_rows = {row.event_id: row for row in db.scalars(select(RequestEventAction).join(RequestEvent).where(RequestEvent.request_id == record.id))}
    for entry, identity in events:
        actor = {"id": identity.user_id if identity else None,
                 "display_name": identity.display_name if identity else "Yapay zekâ / sistem" if entry.actor == "SYSTEM" else ROLES.get(entry.actor, entry.actor) + " (kişi bilgisi kaydedilmemiş)",
                 "role": identity.role if identity else entry.actor, "known": identity is not None or entry.actor == "SYSTEM"}
        timeline.append({"id": f"event-{entry.id}", "kind": "referral" if entry.status == "REFERRED" else "status",
                         "label": STATUSES.get(entry.status, entry.status), "status": entry.status,
                         "actor": actor, "note": entry.note, "at": stamp(entry.created_at)})
        action_row = action_rows.get(entry.id)
        if action_row:
            timeline[-1].update(action=action_row.action, from_status=action_row.from_status,
                                to_status=action_row.to_status, label=entry.note.split(": ", 1)[0])
            if manager:
                timeline[-1]["details"] = json_loads(action_row.details_json, {})
    decisions = db.scalars(select(RequestDecision).where(RequestDecision.request_id == record.id).order_by(RequestDecision.id)).all()
    for decision in decisions:
        delegation = json_loads(decision.original_ai_json, {}).get('audit', {}).get('delegation')
        decision_name = decision.reviewer_name + (' — ' + delegation['delegator_name'] + ' adına vekâleten' if delegation else '')
        timeline.append({"id": f"decision-{decision.id}", "kind": "decision", "label": OUTCOMES[decision.outcome],
                         "outcome": decision.outcome, "actor": {"id": decision.reviewer_id, "display_name": decision_name,
                                                              "role": decision.reviewer_role, "known": True},
                         "note": decision.reason if manager else "İnsan değerlendirmesi kaydedildi.",
                         "at": stamp(decision.created_at)})
    timeline.sort(key=lambda item: item["at"] or "")
    completed = status == "RESOLVED"
    analysis_complete = status in ("REFERRED", "ACTION_PLANNED", "RESOLVED")
    steps = [{"id": "created", "label": "Talep oluşturuldu", "state": "completed"},
             {"id": "analysis", "label": "İhtiyaç analizi", "state": "completed" if analysis_complete else "active"},
             {"id": "design", "label": "Eğitim tasarımı", "state": "active" if status == "REFERRED" else "completed" if active_department and status in ("ACTION_PLANNED", "RESOLVED") else "skipped" if status in ("ACTION_PLANNED", "RESOLVED") else "pending"},
             {"id": "plan", "label": "Çözüm planı", "state": "active" if status == "ACTION_PLANNED" else "completed" if completed else "pending"},
             {"id": "complete", "label": "Çözüme ulaştı", "state": "completed" if completed else "pending"}]
    from .workflow_core import organization_payload, projection
    return {"creator": creator, "organization": organization_payload(db, creator["id"]),
            **projection(db, record, flow, role),
            **action_projection(status, active_department=active_department, creator=creator),
            "steps": steps, "timeline": timeline,
            "pending": not completed, "remaining_steps": [step["label"] for step in steps if step["state"] in ("active", "pending")]}
