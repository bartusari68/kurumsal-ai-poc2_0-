from pathlib import Path
p=Path('app/learning.py');s=p.read_text(encoding='utf-8')
s=s.replace('    from .analysis_pipeline import current_result\n    result = current_result(db, record, flow)', '    from .analysis_pipeline import current_result, latest_run\n    analyzed = latest_run(db, record.id, completed=True)\n    result = current_result(db, record, flow)',1)
s=s.replace('"analysis_created_at": record.created_at.isoformat() + "Z" if record.created_at else None,', '"analysis_run_id": analyzed.id if analyzed else None,\n        "analysis_sequence": analyzed.sequence if analyzed else None,\n        "analysis_created_at": analyzed.completed_at.isoformat() + "Z" if analyzed and analyzed.completed_at else None,')
a=s.index('def validated_feedback_weights(')
s=s[:a]+'''def _intent_decisions(db, canonical_intent, exclude_request_id=None):
    # Feedback belongs to the input that was actually judged, not a later run.
    from .models import AnalysisRun, DecisionAnalysisLink
    from sqlalchemy import or_
    ids = select(RequestRecord.id).where(or_(RequestRecord.canonical_intent == canonical_intent,
        RequestRecord.id.in_(select(AnalysisRun.request_id).where(AnalysisRun.canonical_intent == canonical_intent))))
    if exclude_request_id is not None:
        ids = ids.where(RequestRecord.id != exclude_request_id)
    rows = []
    for decision in _latest_decisions(db, ids):
        link = db.get(DecisionAnalysisLink, decision.id)
        run = db.get(AnalysisRun, link.analysis_run_id) if link else None
        actual = run.canonical_intent if run else db.get(RequestRecord, decision.request_id).canonical_intent
        if actual == canonical_intent:
            rows.append(decision)
    return rows


'''+s[a:]
s=s.replace('    for decision in _latest_decisions(db, ids):\n        if decision.outcome', '    for decision in _intent_decisions(db, canonical_intent):\n        if decision.outcome')
s=s.replace('    rows = _latest_decisions(db, ids)\n    counts = Counter(row.outcome', '    rows = _intent_decisions(db, canonical_intent, exclude_request_id)\n    counts = Counter(row.outcome')
p.write_text(s,encoding='utf-8')
p=Path('app/workflow_policy.py');s=p.read_text(encoding='utf-8')
s=s.replace('    return {"state": state, "scope": scope, "department": department,','    ready = review_ready(db, record, flow) if include_review else True\n    return {"state": state, "scope": scope, "department": department,')
s=s.replace('"analysis_review_ready": review_ready(db, record, flow) if include_review else True,', '"analysis_review_ready": ready,')
s=s.replace('"reviewed": bool(latest and latest.outcome', '"reviewed": bool(ready and latest and latest.outcome')
p.write_text(s,encoding='utf-8')
p=Path('app/static/js/portal.js');s=p.read_text(encoding='utf-8')
s=s.replace("function portalDetailBody(result,admin){\n", "function portalDetailBody(result,admin){\n  var analysis=result.analysis_state,hasAnalysis=!analysis||!!(analysis.latest_completed||analysis.legacy_result);\n")
s=s.replace("(admin?portalReviewReadiness(result):'')", "(admin&&hasAnalysis?portalReviewReadiness(result):'')")
s=s.replace("  var referral=ref?", "  if(!hasAnalysis)brief='';\n  var referral=ref?",1)
s=s.replace('İLK YZ DEĞERLENDİRMESİ', 'GÖSTERİLEN YZ DEĞERLENDİRMESİ').replace('İlk YZ sonucunu ve ihtiyaç bazında ders uyumunu aç', 'Gösterilen YZ sonucunu ve ihtiyaç bazında ders uyumunu aç')
p.write_text(s,encoding='utf-8')
p=Path('tests/frontend.test.cjs');s=p.read_text(encoding='utf-8').replace("html.includes('İLK YAPAY ZEKÂ ÖNERİSİ')", "html.includes('KARARA ESAS AI DEĞERLENDİRMESİ')");p.write_text(s,encoding='utf-8')
