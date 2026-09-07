from pathlib import Path

p = Path('app/workflow.py')
s = p.read_text(encoding='utf-8')
a = s.index('STATUSES =')
b = s.index('\n\n\ndef audience_scope', a)
s = s[:a] + 'from .workflow_policy import STATUSES, DEPARTMENTS\nfrom . import workflow_policy as policy\n' + s[b:]
a = s.index('def change_status(')
b = s.index('\n\ndef refer_request', a)
s = s[:a] + '''def change_status(db, record, flow, *, owner_hash, admin, target, note, expected_version, role="EMPLOYEE", principal=None):
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
''' + s[b:]
s = s.replace('    if flow and flow.status == "RESOLVED":\n        raise HTTPException(409, "Çözülmüş talebi yönlendirmeden önce yeniden incelemeye açın.")', '''    owned_request(db, record.id, principal.token_hash, admin=True, role=principal.role)
    ctx = policy.authorize(db, record, flow, principal.role, "REFER", expected_version)''')
s = s.replace('    referral.department, referral.analysis_summary = department, note', '''    from .workflow_core import transition_effects
    transition_effects(db, record, ctx["state"], "REFERRED")
    from .models import RequestAssignment, RequestSolutionPlan
    assignment = db.get(RequestAssignment, record.id)
    if assignment and assignment.responsible_scope != department:
        assignment.assignee_id = None
    plan = db.get(RequestSolutionPlan, record.id)
    if plan:
        plan.state = "superseded"
    referral.department, referral.analysis_summary = department, note''')
s = s.replace('note=DEPARTMENTS[department] + " birimine yönlendirildi. Analiz: " + note)', 'note=DEPARTMENTS[department] + " birimine yönlendirildi. Analiz: " + note,\n                      action="REFER", from_status=ctx["state"], details={"department": department})')
s = s.replace('    review_allowed = can_review(db, record.id, role)', '    ctx = policy.context(db, record, workflow)\n    review_allowed = policy.permitted("REVIEW", ctx, role)')
s = s.replace('"can_refer": role == "NEEDS_ANALYST"', '"can_refer": policy.permitted("REVIEW_ADVANCE", ctx, role)')
s = s.replace('    payload["process"] = process_summary(db, record, workflow, manager=role in MANAGERS)', '    payload["process"] = process_summary(db, record, workflow, manager=role in MANAGERS, role=role)')
s = s.replace('role == "NEEDS_ANALYST" and payload["status"] != "RESOLVED"', 'policy.permitted("REVIEW_ADVANCE", ctx, role)')
s = s.replace('limit=20, sort="newest"):', 'limit=20, sort="newest", view="", user_id=None):')
s = s.replace('    if search:\n', '    base = base.where(policy.queue_condition(view, role, user_id))\n    if search:\n', 1)
s = s.replace('**action_projection(state, active_department=active_department, creator=creator)})', '''**action_projection(state, active_department=active_department, creator=creator),
                      **_queue_projection(db, record, flow, role)})''')
s = s.replace('    return {"items": items, "total": total,', '''    from .models import RequestAssignment
    has_assignment = db.scalar(select(RequestRecord.id).outerjoin(RequestWorkflow).where(scope,
        policy.queue_condition("assigned", role, user_id)).limit(1)) is not None
    return {"queue_views": policy.queue_views(role, has_assignment), "items": items, "total": total,''')
s += '''

def _queue_projection(db, record, flow, role):
    from .workflow_core import aging
    ctx = policy.context(db, record, flow)
    last = db.scalar(select(RequestEvent).where(RequestEvent.request_id == record.id).order_by(RequestEvent.created_at.desc(), RequestEvent.id.desc()).limit(1))
    return {"current_stage": STATUSES[ctx["state"]], "responsible_scope": ctx["scope"],
            "assignee": ctx["assignee"], "aging": aging(db, record, flow, ctx),
            "last_action": {"note": last.note, "at": stamp(last.created_at)} if last else None}
'''
p.write_text(s, encoding='utf-8')

p = Path('app/process.py')
s = p.read_text(encoding='utf-8')
s = s.replace('def add_process_event(db, *, request_id, status, actor, note, principal=None, owner_hash=None):', 'def add_process_event(db, *, request_id, status, actor, note, principal=None, owner_hash=None, action=None, from_status=None, details=None):')
s = s.replace('    return entry\n', '''    if action:
        from .models import RequestEventAction
        from .utils import json_dumps
        db.add(RequestEventAction(event=entry, action=action, from_status=from_status or status,
                                  to_status=status, details_json=json_dumps(details or {})))
    return entry
''', 1)
a = s.index('    from .workflow import DEPARTMENTS\n', s.index('def action_projection'))
b = s.index('\n\ndef process_summary', a)
s = s[:a] + '''    from .workflow_policy import owner_scope, STATES, DEPARTMENTS
    owner = owner_scope(status, active_department)
    _, next_code, next_label = STATES.get(status, STATES["LEGACY"])
    label = DEPARTMENTS.get(owner, "İhtiyaç Analizi Ekibi" if owner == "NEEDS_ANALYST" else ROLES.get(owner, "Tamamlandı"))
    return {"current_owner": {"role": owner, "label": label}, "next_action": {"code": next_code, "label": next_label}}
''' + s[b:]
s = s.replace('def process_summary(db, record, flow, *, manager=False):', 'def process_summary(db, record, flow, *, manager=False, role="EMPLOYEE"):')
s = s.replace('    for entry, identity in events:\n', '''    from .models import RequestEventAction
    from .utils import json_loads
    action_rows = {row.event_id: row for row in db.scalars(select(RequestEventAction).join(RequestEvent).where(RequestEvent.request_id == record.id))}
    for entry, identity in events:
''')
s = s.replace('    decisions = db.scalars', '''        action_row = action_rows.get(entry.id)
        if action_row:
            timeline[-1].update(kind="action", action=action_row.action, from_status=action_row.from_status,
                                to_status=action_row.to_status, label=entry.note.split(": ", 1)[0])
            if manager:
                timeline[-1]["details"] = json_loads(action_row.details_json, {})
    decisions = db.scalars''')
s = s.replace('    return {"creator": creator, "organization": {"name": None, "label": "Organizasyon bilgisi tanımlanmamış", "known": False},', '''    from .workflow_core import organization_payload, projection
    return {"creator": creator, "organization": organization_payload(db, creator["id"]),
            **projection(db, record, flow, role),''')
p.write_text(s, encoding='utf-8')

p = Path('app/learning.py')
s = p.read_text(encoding='utf-8')
a = s.index('DEPARTMENTS =')
b = s.index('\nOUTCOMES', a)
s = s[:a] + 'from .workflow_policy import DEPARTMENTS\nfrom . import workflow_policy as policy' + s[b:]
s = s.replace('    result = json_loads(flow.result_json, {}) if flow else {}\n    support = decision_support(result, record.text)', '''    ctx = policy.authorize(db, record, flow, principal.role, "REVIEW_ADVANCE" if advance else "REVIEW", expected_version)
    result = json_loads(flow.result_json, {}) if flow else {}
    support = decision_support(result, record.text)''')
a = s.index('        if flow and flow.status == "RESOLVED":', s.index('    if advance:\n        from .process import resolve_routing'))
b = s.index('    if not flow:', a)
s = s[:a] + '''        next_status = policy.review_target(outcome=outcome, training=values["training_need_confirmed"],
            critical=classification.get("risk_level") == "KRITIK", support_action=support["action"],
            course_id=course_id, missing=missing)
        if next_status == "REFERRED":
            destination = resolve_routing(db, record, flow, category=category,
                department=values.get("routing_department") or (department if outcome == "MODIFIED" else None))
            if not destination["resolved"]:
                raise HTTPException(422, "Bu kapsam için sorumlu birim tanımlı değil. Değerlendirme içindeki hedef birim alanından seçim yapın.")
''' + s[b:]
s = s.replace('        add_process_event(db, request_id=record.id, status=next_status, actor=principal.role, principal=principal, note=note)', '''        from .workflow_core import transition_effects, write_plan
        transition_effects(db, record, ctx["state"], next_status)
        if next_status == "ACTION_PLANNED":
            course = db.get(Course, course_id)
            write_plan(db, record, flow, principal, summary=(course.name + ": " if course else "") + reason,
                       scope="NEEDS_ANALYST")
        from .models import RequestAssignment, RequestSolutionPlan
        assignment = db.get(RequestAssignment, record.id)
        if assignment and destination and assignment.responsible_scope != destination["department"]:
            assignment.assignee_id = None
        if next_status == "REFERRED":
            old_plan = db.get(RequestSolutionPlan, record.id)
            if old_plan:
                old_plan.state = "superseded"
        add_process_event(db, request_id=record.id, status=next_status, actor=principal.role, principal=principal,
                          note=note, action="REVIEW_ADVANCE", from_status=ctx["state"], details={"outcome": outcome, "routing": destination})''')
p.write_text(s, encoding='utf-8')

p = Path('app/schemas.py')
s = p.read_text(encoding='utf-8') + '''

class WorkflowActionRequest(BaseModel):
    action: str = Field(min_length=1, max_length=40)
    expected_version: int = Field(ge=0)
    note: str = Field(default="", max_length=3000)
    summary: str | None = Field(default=None, min_length=10, max_length=3000)
    responsible_unit: str | None = Field(default=None, max_length=40)
    assignee_id: int | None = Field(default=None, gt=0)
    target_date: __import__('datetime').date | None = None
'''
s = s.replace('from typing import Literal', 'from typing import Literal\nfrom datetime import date')
s = s.replace("__import__('datetime').date", 'date')
p.write_text(s, encoding='utf-8')

p = Path('app/main.py')
s = p.read_text(encoding='utf-8')
s = s.replace('Base.metadata.create_all(bind=engine)', 'from .schemas import WorkflowActionRequest\nfrom .workflow_core import execute_action\n\nBase.metadata.create_all(bind=engine)', 1)
s = s.replace('def my_requests(status: str | None = None,', 'def my_requests(view: str = Query("", max_length=20), status: str | None = None,')
s = s.replace('def admin_requests(status: str | None = None,', 'def admin_requests(view: str = Query("", max_length=20), status: str | None = None,')
s = s.replace('search=search, sort=sort, offset=offset, limit=limit)', 'search=search, sort=sort, offset=offset, limit=limit, view=view, user_id=session.user_id)')
s += '''

@app.post("/api/requests/{request_id}/actions")
def employee_action(request_id: int, payload: WorkflowActionRequest, session=Depends(require_employee), db: Session = Depends(get_db)):
    record, flow = owned_request(db, request_id, session.token_hash)
    return execute_action(db, record, flow, session, payload)


@app.post("/api/admin/requests/{request_id}/actions")
def manager_action(request_id: int, payload: WorkflowActionRequest, session=Depends(require_admin), db: Session = Depends(get_db)):
    record, flow = owned_request(db, request_id, session.token_hash, admin=True, role=session.role)
    return execute_action(db, record, flow, session, payload)
'''
p.write_text(s, encoding='utf-8')
