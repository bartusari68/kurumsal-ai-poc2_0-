from pathlib import Path
p=Path('app/services.py');s=p.read_text(encoding='utf-8')
s=s.replace('async def analyze_request(db: Session, text: str, owner_hash: str = "") -> dict:', 'async def compute_analysis(db: Session, text: str) -> dict:\n    """Compute a validated result without creating or modifying request records."""')
s=s.replace('    db.add(record)\n    db.flush()\n\n    grouped:', '    grouped:')
a=s.index('    for course_id, items in grouped.items():',s.index('async def compute_analysis'))
b=s.index('    course_summaries = []',a)
s=s[:a]+s[b:]
s=s.replace('    record_analysis(db, record, result, owner_hash)\n    db.commit()\n    db.refresh(record)\n    return result', '    return result\n\n\n# Internal compatibility name; persistence now belongs to analysis_pipeline.\nanalyze_request = compute_analysis')
s=s.replace('from .workflow import record_analysis\n','')
p.write_text(s,encoding='utf-8')

p=Path('app/schemas.py');s=p.read_text(encoding='utf-8')
s=s.replace('class AnalyzeRequest(BaseModel):\n    text:', 'class AnalyzeRequest(BaseModel):\n    idempotency_key: str | None = Field(default=None, min_length=8, max_length=80)\n    text:')
s+='''

class AnalysisRetryRequest(BaseModel):
    expected_version: int = Field(ge=0)
    idempotency_key: str = Field(min_length=8, max_length=80)
'''
p.write_text(s,encoding='utf-8')

p=Path('app/main.py');s=p.read_text(encoding='utf-8')
s=s.replace('from .database import Base, engine, get_db','from .database import Base, engine, get_db, SessionLocal')
s=s.replace('install_decision_guards\n','install_decision_guards, install_analysis_guards\n')
s=s.replace('install_decision_guards(engine)','install_decision_guards(engine)\ninstall_analysis_guards(engine)')
s=s.replace('    yield\n    await asyncio.to_thread(local_models.close)', '''    from .analysis_pipeline import worker
    task = asyncio.create_task(worker(SessionLocal))
    try:
        yield
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        await asyncio.to_thread(local_models.close)''')
a=s.index('@app.post("/api/requests/analyze")')
b=s.index('\n\n@app.post(',a+6)
s=s[:a]+'''@app.post("/api/requests/analyze", status_code=202)
def analyze(payload: AnalyzeRequest, db: Session = Depends(get_db), session=Depends(require_employee)):
    from .analysis_pipeline import persist_request
    record, flow = persist_request(db, payload.text, session, payload.idempotency_key)
    result = request_detail(db, record, flow)
    result["message"] = "Talebiniz kaydedildi. Analiz durumu talep detayından takip edilebilir."
    return result
'''+s[b:]
s+='''

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
'''
p.write_text(s,encoding='utf-8')

p=Path('app/workflow.py');s=p.read_text(encoding='utf-8')
s=s.replace('    result = json_loads(workflow.result_json, {}) if workflow else {}', '    from .analysis_pipeline import current_result, analysis_projection\n    result = current_result(db, record, workflow)')
s=s.replace('    payload["process"] = process_summary', '    payload["analysis_state"] = analysis_projection(db, record, workflow, role)\n    payload["process"] = process_summary')
s=s.replace('        result = json_loads(flow.result_json, {}) if flow else {}', '        from .analysis_pipeline import current_result\n        result = current_result(db, record, flow)')
s=s.replace('"topic": record.topic,','"topic": classification.get("topic") or record.topic,')
# No misleading legacy-results placeholder for a newly saved pending/failed request.
s=s.replace('    if not result:\n        result =', '    if not result:\n        from .analysis_pipeline import latest_run\n        pending_analysis = latest_run(db, record.id) is not None\n        result =')
s=s.replace('"Bu kayıt önceki analiz sürümüne aittir; yeni uyum yüzdesi hesaplanmamıştır."', '"Henüz başarılı bir AI analizi bulunmuyor. Talebiniz kayıtlıdır." if pending_analysis else "Bu kayıt önceki analiz sürümüne aittir; yeni uyum yüzdesi hesaplanmamıştır."')
p.write_text(s,encoding='utf-8')

p=Path('app/workflow_policy.py');s=p.read_text(encoding='utf-8')
s=s.replace('    result = json_loads(flow.result_json, {}) if flow else {}\n    latest = db.scalar(select(RequestDecision.outcome)', '    from .analysis_pipeline import current_result, review_ready, decision_is_current\n    result = current_result(db, record, flow)\n    latest = db.scalar(select(RequestDecision)')
s=s.replace('"reviewed": latest in ("APPROVED", "MODIFIED")', '"analysis_review_ready": review_ready(db, record, flow) if include_review else True,\n            "reviewed": bool(latest and latest.outcome in ("APPROVED", "MODIFIED") and decision_is_current(db, latest, record, flow))')
s=s.replace('    if rule.owner_only and role != ctx["scope"]:', '    if code in ("REVIEW", "REVIEW_ADVANCE") and not ctx.get("analysis_review_ready", True):\n        return False\n    if rule.owner_only and role != ctx["scope"]:')
p.write_text(s,encoding='utf-8')

p=Path('app/workflow_core.py');s=p.read_text(encoding='utf-8')
s=s.replace('        db.commit()\n        db.refresh(flow)', '''        if code == "PROVIDE_INFO":
            from .analysis_pipeline import enqueue_extra_info
            db.flush()
            enqueue_extra_info(db, record, flow, principal)
        db.commit()
        db.refresh(flow)''')
p.write_text(s,encoding='utf-8')

p=Path('app/process.py');s=p.read_text(encoding='utf-8')
s=s.replace('    result = json_loads(flow.result_json, {}) if flow else {}', '    from .analysis_pipeline import current_result, decision_is_current\n    result = current_result(db, record, flow)')
s=s.replace('        latest_department = human_routing_department(latest) if latest else None','        if latest and not decision_is_current(db, latest, record, flow):\n            latest = None\n        latest_department = human_routing_department(latest) if latest else None')
p.write_text(s,encoding='utf-8')

p=Path('app/learning.py');s=p.read_text(encoding='utf-8')
s=s.replace('    result = json_loads(flow.result_json, {}) if flow else {}', '    from .analysis_pipeline import current_result\n    result = current_result(db, record, flow)',1)
s=s.replace('    db.add(RequestDecision(request_id=record.id,', '    decision = RequestDecision(request_id=record.id,',1)
s=s.replace('        created_at=datetime.utcnow()))\n    if advance:', '''        created_at=datetime.utcnow())
    db.add(decision)
    db.flush()
    from .analysis_pipeline import latest_run
    from .models import DecisionAnalysisLink
    analyzed = latest_run(db, record.id, completed=True)
    if analyzed:
        db.add(DecisionAnalysisLink(decision_id=decision.id, analysis_run_id=analyzed.id))
    if advance:''')
s=s.replace('"request_version": row.request_version, "original_ai": original}', '"request_version": row.request_version, "analysis_version": __import__("app.analysis_pipeline", fromlist=["decision_reference"]).decision_reference(db, row), "original_ai": original}')
s=s.replace('    from .workflow import stamp\n', '    from .workflow import stamp\n    from .analysis_pipeline import decision_reference\n',1)
s=s.replace('__import__("app.analysis_pipeline", fromlist=["decision_reference"]).decision_reference(db, row)', 'decision_reference(db, row)')
# Current reporting must not present a historical verdict as a verdict on a new result.
s=s.replace('    latest = {row.request_id: row for row in _latest_decisions(db, ids)}', '''    from .analysis_pipeline import current_result, decision_is_current
    pair_map = {record.id: (record, flow) for record, flow in pairs}
    latest = {row.request_id: row for row in _latest_decisions(db, ids)
              if decision_is_current(db, row, *pair_map[row.request_id])}''')
s=s.replace('        stage_counts[row.reviewer_role][row.outcome] += 1', '        if decision_is_current(db, row, *pair_map[row.request_id]):\n            stage_counts[row.reviewer_role][row.outcome] += 1')
s=s.replace('        result = json_loads(flow.result_json, {}) if flow else {}', '        result = current_result(db, record, flow)')
p.write_text(s,encoding='utf-8')
