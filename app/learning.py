"""Audited human feedback and evidence-bounded retrieval; no model training occurs."""
from .time_policy import utc_now, as_utc, utc_stamp
from collections import Counter, defaultdict
from datetime import datetime
import math

from fastapi import HTTPException
from sqlalchemy import func, select, update

from .indexing import active_course_ids, fingerprint, source_path
from .models import Course, RequestDecision, RequestRecord, RequestReferral, RequestWorkflow
from .portal_auth import MANAGERS
from .taxonomy import INDEX, normalize_category
from .utils import canonicalize, json_dumps, json_loads

from .workflow_policy import DEPARTMENTS
from . import workflow_policy as policy
OUTCOMES = {"APPROVED": "Onaylandı", "MODIFIED": "Düzeltilerek onaylandı", "REJECTED": "Yanlış bulundu"}
ROUTING_VERSION = "explicit-domain-routing-v1"


def department_suggestion(classification):
    """Only configured domain rules propose units; absence never guesses ownership."""
    category = str(classification.get("subcategory_id", "")).split(".")[0]
    if category in ("ENGINEERING", "SOFTWARE"):
        identifier, reason = "ENGINEERING_DESIGN", "Ürün, sistem veya yazılım mühendisliği kapsamı için tanımlı yönlendirme kuralı."
    elif category == "OPERATIONS":
        identifier, reason = "TECHNICAL_DESIGN", "Üretim, bakım veya operasyon kapsamı için tanımlı yönlendirme kuralı."
    else:
        identifier, reason = None, "Bu konu için doğrulanmış bir birim eşlemesi yok. İhtiyaç analizi sorumlu birimi seçmelidir."
    return {"id": identifier, "label": DEPARTMENTS.get(identifier, "İhtiyaç analizi kararı bekleniyor"),
            "reason": reason, "rule_version": ROUTING_VERSION}


def _topics(values):
    if not isinstance(values, list):
        return []
    return list(dict.fromkeys(value.strip() for value in values if isinstance(value, str) and value.strip()))[:20]


def decision_support(result, text=""):
    classification, coverage = result.get("classification", {}), result.get("coverage", {})
    percent = coverage.get("fit_percent")
    if not isinstance(percent, (int, float)) or isinstance(percent, bool) or not math.isfinite(percent) or not 0 <= percent <= 100:
        percent = None
    requirements = [item.get("label", "") for item in classification.get("requirements", []) if isinstance(item, dict)]
    missing = _topics(coverage.get("missing_topics", []))
    courses = result.get("courses", [])
    top = courses[0] if courses else None
    existing = {"course_id": top.get("course_id"), "course_name": top.get("course_name")} if top and percent is not None and percent > 40 else None
    need_type = classification.get("need_type")
    if classification.get("risk_level") == "KRITIK" or need_type == "KRITIK_ICERIK":
        action, label = "URGENT_REVIEW", "Öncelikli insan incelemesi"
    elif need_type in ("SUREC_ARAC", "PERFORMANS_DESTEGI", "BILGI"):
        action, label = "NON_TRAINING", "Eğitim dışı çözüm ihtiyacını incele"
    elif percent is None:
        action, label = "CLARIFY", "Kapsamı netleştir ve yeniden analiz et"
    elif percent <= 40:
        action, label = "NEW_COURSE", "Yeni ders ihtiyacı taslağını incele"
    elif coverage.get("status") == "VAR" and percent >= 95 and not missing:
        action, label = "USE_COURSE", "Mevcut dersin uygunluğunu onayla"
    else:
        action, label = "ENRICH_COURSE", "Mevcut dersin eksik kapsamını zenginleştir"
    if action == "NEW_COURSE" and not missing:
        missing = _topics(requirements)
    information = ["Hedef katılımcı grubu ve mevcut yetkinlik seviyesi", "İş üzerinde beklenen ölçülebilir çıktı", "Katılımcı sayısı, zaman ve öncelik"]
    if not requirements:
        information.insert(0, "Talebin somut öğrenme veya çözüm hedefleri")
    return {"action": action, "action_label": label, "fit_percent": percent,
            "suggested_department": department_suggestion(classification), "missing_topics": missing,
            "excess_topics": [], "human_confirmation_required": True,
            "brief": {"title": classification.get("topic") or "Eğitim / çözüm ihtiyacı",
                      "need_summary": text, "learning_objectives": _topics(requirements),
                      "missing_content": missing, "existing_course": existing, "information_needed": information},
            "explanation": "Bu taslak analiz kararına yardımcı olur. Analiz ekibinin onayı eğitim ihtiyacını doğrular; bilinen hedefe yönlendirme aynı işlemde tamamlanır."}


def can_review(db, request_id, role):
    if role == "NEEDS_ANALYST":
        return True
    if role not in DEPARTMENTS:
        return False
    referral = db.get(RequestReferral, request_id)
    return bool(referral and referral.active and referral.training_need_confirmed and referral.department == role)


def human_routing_department(decision):
    """An approved AI verdict may have a distinct, explicitly assigned work target."""
    snapshot = json_loads(decision.original_ai_json, {})
    advancement = snapshot.get("audit", {}).get("advancement", {})
    routing = advancement.get("routing") or {}
    return routing.get("department") or decision.actual_department


def decision_history(db, request_id, *, include_audit=False):
    rows = db.scalars(select(RequestDecision).where(RequestDecision.request_id == request_id).order_by(RequestDecision.id.desc())).all()
    from .workflow import stamp
    from .analysis_pipeline import decision_reference
    output = []
    for row in rows:
        original = json_loads(row.original_ai_json, {})
        advancement = original.get("audit", {}).get("advancement", {})
        if not include_audit:
            original.pop("audit", None)
        # Frozen public-shaped AI observation contains no raw document excerpts or provider data.
        output.append({"id": row.id, "outcome": row.outcome, "outcome_label": OUTCOMES[row.outcome], "reason": row.reason,
                       "reviewer": {"id": row.reviewer_id, "display_name": row.reviewer_name, "role": row.reviewer_role},
                       "actual_subcategory_id": row.actual_subcategory_id, "actual_category": normalize_category(row.actual_subcategory_id)["category"],
                       "actual_department": row.actual_department, "actual_course_id": row.actual_course_id,
                       "routing": advancement.get("routing"), "next_status": advancement.get("status"),
                       "training_need_confirmed": row.training_need_confirmed,
                       "missing_topics": json_loads(row.missing_topics_json, []), "excess_topics": json_loads(row.excess_topics_json, []),
                       "changed_fields": json_loads(row.changed_fields_json, []), "created_at": stamp(row.created_at),
                       "request_version": row.request_version, "analysis_version": decision_reference(db, row), "original_ai": original})
    return output


def review_options(db):
    try:
        active = active_course_ids(db)
    except OSError:
        active = []
    return {"courses": [{"id": course.id, "name": course.name} for course in db.scalars(
        select(Course).where(Course.id.in_(active)).order_by(Course.name)).all()],
        "routing_by_category": {identifier: department_suggestion({"subcategory_id": identifier}) for identifier in INDEX}}


def _validated_source(db, course_id):
    try:
        if course_id not in active_course_ids(db):
            return ""
        course = db.get(Course, course_id)
        return fingerprint(source_path(course.pdf_path)) if course else ""
    except OSError:
        return ""


def record_decision(db, record, flow, principal, payload, *, advance=False):
    """Atomic version check, actor from session, append-only judgement with AI snapshot."""
    from .workflow import owned_request, public_result, request_detail
    if principal.role not in MANAGERS:
        raise HTTPException(403, "İnsan değerlendirmesi için yönetici yetkisi gerekir.")
    if advance and principal.role != "NEEDS_ANALYST":
        raise HTTPException(403, "Değerlendirme ve yönlendirme işlemi ihtiyaç analizi yöneticisine aittir.")
    owned_request(db, record.id, principal.token_hash, admin=True, role=principal.role)
    if not can_review(db, record.id, principal.role):
        raise HTTPException(403, "Yalnızca analiz ekibi veya talebin yönlendirildiği birim değerlendirebilir.")
    values = payload.model_dump() if hasattr(payload, "model_dump") else dict(payload)
    outcome, reason = values.get("outcome"), str(values.get("reason") or "").strip()
    if outcome not in OUTCOMES or not 10 <= len(reason) <= 3000:
        raise HTTPException(422, "Geçerli karar türü ve en az 10 karakterlik gerekçe gerekir.")
    expected_version = values.get("expected_version")
    if expected_version != (flow.version if flow else 0):
        raise HTTPException(409, "Talep başka bir işlemde güncellendi. Yeniden açın.")
    ctx = policy.authorize(db, record, flow, principal.role, "REVIEW_ADVANCE" if advance else "REVIEW", expected_version)
    from .analysis_pipeline import current_result, latest_run
    analyzed = latest_run(db, record.id, completed=True)
    result = current_result(db, record, flow)
    support = decision_support(result, record.text)
    classification = result.get("classification", {})
    baseline_category = normalize_category(classification.get("subcategory_id"))["subcategory_id"]
    baseline_department = support["suggested_department"]["id"]
    baseline_course = (support["brief"]["existing_course"] or {}).get("course_id")
    baseline_training = True if support["action"] in ("NEW_COURSE", "ENRICH_COURSE", "USE_COURSE") else False if support["action"] == "NON_TRAINING" else None
    if values.get("training_need_confirmed") is None:
        if outcome == "MODIFIED":
            raise HTTPException(422, "Düzeltilen talebin eğitim ihtiyacı mı yoksa eğitim dışı çözüm mü olduğunu seçin.")
        # Approving a request for clarification never invents training confirmation.
        values["training_need_confirmed"] = outcome == "APPROVED" and baseline_training is True
    if not isinstance(values["training_need_confirmed"], bool):
        raise HTTPException(422, "Eğitim ihtiyacının doğrulanma durumu geçersiz.")
    category = values.get("actual_subcategory_id") or baseline_category
    if category not in INDEX:
        raise HTTPException(422, "Geçerli bir alt kategori seçin.")
    department, course_id = values.get("actual_department"), values.get("actual_course_id")
    if outcome == "APPROVED":
        department = department or baseline_department
        course_id = course_id if course_id is not None else baseline_course
    if department is not None and department not in DEPARTMENTS:
        raise HTTPException(422, "Geçerli bir eğitim tasarım birimi seçin.")
    missing = support["missing_topics"] if values.get("missing_topics") is None else values["missing_topics"]
    excess = [] if values.get("excess_topics") is None else values["excess_topics"]
    for topics in (missing, excess):
        if not isinstance(topics, list) or len(topics) > 20 or any(not isinstance(item, str) or not item.strip() or len(item) > 300 for item in topics):
            raise HTTPException(422, "Kapsam başlıkları boş olamaz; en çok 20 başlık ve başlık başına 300 karakter kullanın.")
    missing, excess = _topics(missing), _topics(excess)
    changed = []
    for name, actual, original in (("subcategory", category, baseline_category), ("department", department, baseline_department),
                                    ("course", course_id, baseline_course), ("missing_topics", missing, support["missing_topics"]),
                                    ("excess_topics", excess, [])):
        if actual != original:
            changed.append(name)
    if values["training_need_confirmed"] != baseline_training and (baseline_training is not None or outcome == "MODIFIED"):
        changed.append("training_need_confirmed")
    if outcome == "APPROVED" and changed:
        if changed == ["training_need_confirmed"]:
            raise HTTPException(422, "AI eğitim önerisini onaylamak için eğitim ihtiyacını doğrulayın. Eğitim dışı bir ihtiyaç belirlediyseniz düzeltme seçeneğini kullanın.")
        raise HTTPException(422, "AI önerisini değiştirdiğinizde 'Düzeltilerek onaylandı' seçeneğini kullanın.")
    if outcome == "MODIFIED" and not changed:
        raise HTTPException(422, "Düzeltme için kategori, birim, ders veya kapsamda en az bir değişiklik belirtin.")
    digest = _validated_source(db, course_id) if course_id is not None else ""
    if course_id is not None and not digest:
        raise HTTPException(422, "Seçilen dersin PDF kaynağı güncel ve erişilebilir olmalıdır.")
    original_course = next((course for course in result.get("courses", []) if course.get("course_id") == course_id), None)
    original_hashes = {item["source_hash"] for item in (original_course or {}).get("evidence", []) if item.get("source_hash")}
    if outcome != "REJECTED" and original_hashes and original_hashes != {digest}:
        raise HTTPException(409, "Ders PDF'si analizden sonra değişti. Eski analizi onaylamadan önce güncel içerikle yeniden değerlendirin.")
    if outcome == "APPROVED" and not result:
        raise HTTPException(422, "Önceki kayıtta doğrulanabilir bir AI değerlendirmesi yok; düzeltme veya ret gerekçesi kaydedin.")
    destination = None
    next_status = None
    if advance:
        from .process import resolve_routing
        next_status = policy.review_target(outcome=outcome, training=values["training_need_confirmed"],
            critical=classification.get("risk_level") == "KRITIK", support_action=support["action"],
            course_id=course_id, missing=missing)
        if next_status == "REFERRED":
            destination = resolve_routing(db, record, flow, category=category,
                department=values.get("routing_department") or (department if outcome == "MODIFIED" else None))
            if not destination["resolved"]:
                raise HTTPException(422, "Bu kapsam için sorumlu birim tanımlı değil. Değerlendirme içindeki hedef birim alanından seçim yapın.")
    from .workflow_core import lock_flow
    version = expected_version + 1
    transition = {"status": next_status, "public_note": reason} if advance else {}
    flow = lock_flow(db, record, flow, expected_version, **transition)
    snapshot = public_result(result)
    # Retain taxonomy IDs, proposal and requirements required to audit corrections.
    snapshot["classification"] = {key: classification.get(key) for key in (
        "category_id", "category", "subcategory_id", "subcategory", "topic", "need_type", "risk_level", "requirements")}
    snapshot["decision_support"] = support
    from .config import settings
    snapshot["audit"] = {"analysis": result, "provenance": {
        "analysis_run_id": analyzed.id if analyzed else None,
        "analysis_sequence": analyzed.sequence if analyzed else None,
        "analysis_created_at": utc_stamp(analyzed.completed_at) if analyzed and analyzed.completed_at else None,
        "snapshot_created_at": utc_stamp(utc_now()),
        "analysis_mode": result.get("ai_mode"), "llm_model_at_review": settings.llm_model,
        "embedding_model_at_review": settings.embedding_model,
        "policy_version": result.get("coverage", {}).get("policy_version"),
        "note": "Model ayarı değerlendirme anında kaydedilmiştir; eski analizde model bilgisi yoksa geçmiş model sürümü çıkarılamaz."},
        "selected_course_validation": {"course_id": course_id, "source_hash": digest,
            "analysis_source_hashes": sorted(original_hashes), "analysis_source_verified": bool(original_hashes),
            "selection_origin": "analysis_candidate" if original_course else "manual_selection" if course_id else "no_course"}}
    if principal.delegation:
        snapshot['audit']['delegation'] = dict(principal.delegation)
    if advance:
        snapshot["audit"]["advancement"] = {"status": next_status, "routing": destination,
                                            "policy": "human-review-and-advance-v1"}
    decision = RequestDecision(request_id=record.id, reviewer_id=principal.user_id, reviewer_name=principal.display_name,
        reviewer_role=principal.role, request_version=version, outcome=outcome, reason=reason,
        original_ai_json=json_dumps(snapshot), actual_subcategory_id=category, actual_department=department,
        actual_course_id=course_id, course_source_hash=digest, training_need_confirmed=values["training_need_confirmed"],
        missing_topics_json=json_dumps(missing), excess_topics_json=json_dumps(excess), changed_fields_json=json_dumps(changed),
        created_at=utc_now())
    db.add(decision)
    db.flush()
    from .analysis_pipeline import latest_run
    from .models import DecisionAnalysisLink
    analyzed = latest_run(db, record.id, completed=True)
    if analyzed:
        db.add(DecisionAnalysisLink(decision_id=decision.id, analysis_run_id=analyzed.id))
    if advance:
        from .process import add_process_event
        referral = db.get(RequestReferral, record.id)
        if next_status == "REFERRED":
            if not referral:
                referral = RequestReferral(request_id=record.id)
                db.add(referral)
            referral.department, referral.analysis_summary = destination["department"], reason
            referral.training_need_confirmed, referral.active = True, True
            referral.analyst_id, referral.completed_at = principal.user_id, utc_now()
            note = destination["department_label"] + " birimine yönlendirildi. Analiz: " + reason
        else:
            if referral:
                referral.active = False
            note = ("Mevcut ders ile çözüm planlandı. " if next_status == "ACTION_PLANNED" else "Değerlendirme kaydedildi; analiz ekibinde inceleme sürüyor. ") + reason
        from .workflow_core import transition_effects, write_plan
        transition_effects(db, record, ctx["state"], next_status)
        if next_status == "ACTION_PLANNED":
            course = db.get(Course, course_id)
            write_plan(db, record, flow, principal, summary=(course.name + ": " if course else "") + reason,
                       scope="NEEDS_ANALYST", from_status=ctx["state"])
        from .models import RequestAssignment, RequestSolutionPlan
        assignment = db.get(RequestAssignment, record.id)
        if assignment and destination and assignment.responsible_scope != destination["department"]:
            assignment.assignee_id = None
        if next_status == "REFERRED":
            old_plan = db.get(RequestSolutionPlan, record.id)
            if old_plan:
                old_plan.state = "superseded"
        add_process_event(db, request_id=record.id, status=next_status, actor=principal.role, principal=principal,
                          note=note, action="REVIEW_ADVANCE", from_status=ctx["state"], details={"outcome": outcome, "routing": destination})
    db.commit()
    db.refresh(flow)
    return request_detail(db, record, flow, admin=principal.role == "NEEDS_ANALYST", role=principal.role)


def record_decision_and_advance(db, record, flow, principal, payload):
    """One version lock and commit for verdict, routing, state and actor audit."""
    try:
        return record_decision(db, record, flow, principal, payload, advance=True)
    except Exception:
        db.rollback()
        raise


def _latest_decisions(db, request_ids=None):
    latest = select(func.max(RequestDecision.id)).group_by(RequestDecision.request_id)
    if request_ids is not None:
        latest = latest.where(RequestDecision.request_id.in_(request_ids))
    return db.scalars(select(RequestDecision).where(RequestDecision.id.in_(latest))).all()


def _intent_decisions(db, canonical_intent, exclude_request_id=None):
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


def validated_feedback_weights(db, canonical_intent):
    """A request supplies at most one vote; changed/deleted sources revoke the vote."""
    if not canonical_intent:
        return {}
    ids = select(RequestRecord.id).where(RequestRecord.canonical_intent == canonical_intent)
    votes = Counter()
    hashes = {}
    for decision in _intent_decisions(db, canonical_intent):
        if decision.outcome == "REJECTED" or not decision.training_need_confirmed or decision.actual_course_id is None:
            continue
        course_id = decision.actual_course_id
        if course_id not in hashes:
            hashes[course_id] = _validated_source(db, course_id)
        if hashes[course_id] and hashes[course_id] == decision.course_source_hash:
            votes[course_id] += 1
    # Bounded search priority only. Suitability percentages remain evidence-based.
    return {course_id: round(min(.05, count * .01), 3) for course_id, count in votes.items()}


def prior_case_support(db, canonical_intent, *, exclude_request_id=None):
    """Aggregate explicit human decisions for analysts; never relabel the AI silently."""
    if not canonical_intent:
        return {"sample_count": 0, "category_votes": [], "department_votes": [], "has_conflict": False}
    ids = select(RequestRecord.id).where(RequestRecord.canonical_intent == canonical_intent)
    if exclude_request_id is not None:
        ids = ids.where(RequestRecord.id != exclude_request_id)
    rows = _intent_decisions(db, canonical_intent, exclude_request_id)
    counts = Counter(row.outcome for row in rows)
    categories, departments = Counter(), Counter()
    for row in rows:
        if row.outcome == "REJECTED":
            continue
        categories[row.actual_subcategory_id] += 1
        department = human_routing_department(row)
        if department in DEPARTMENTS and row.training_need_confirmed:
            departments[department] += 1
    return {"sample_count": len(rows), "approved": counts["APPROVED"], "modified": counts["MODIFIED"], "rejected": counts["REJECTED"],
            "category_votes": [{"id": key, "label": normalize_category(key)["subcategory"], "count": count} for key, count in categories.most_common()],
            "department_votes": [{"id": key, "label": DEPARTMENTS[key], "count": count} for key, count in departments.most_common()],
            "has_conflict": len(categories) > 1 or len(departments) > 1,
            "explanation": "Aynı niyet için her önceki talebin son insan kararı bir örnektir. Bu geçmiş dağılımı AI sınıflandırmasını değiştirmez; analist öneriyi ayrıca doğrular."}


def review_report(db, principal):
    from .workflow import audience_scope
    if principal.role not in MANAGERS:
        raise HTTPException(403, "Karar raporu yönetici yetkisi gerektirir.")
    pairs = db.execute(select(RequestRecord, RequestWorkflow).outerjoin(RequestWorkflow).where(
        audience_scope(principal.token_hash, True, principal.role))).all()
    ids = [record.id for record, _ in pairs]
    from .analysis_pipeline import current_result, decision_is_current
    pair_map = {record.id: (record, flow) for record, flow in pairs}
    latest = {row.request_id: row for row in _latest_decisions(db, ids)
              if decision_is_current(db, row, *pair_map[row.request_id])}
    counts = Counter(row.outcome for row in latest.values())
    total_history = db.scalar(select(func.count(RequestDecision.id)).where(RequestDecision.request_id.in_(ids))) or 0
    reviewed = len(latest)
    gaps, extras, confirmed_gaps, confirmed_extras = defaultdict(set), defaultdict(set), defaultdict(set), defaultdict(set)
    stage_latest = select(func.max(RequestDecision.id)).where(RequestDecision.request_id.in_(ids)).group_by(
        RequestDecision.request_id, RequestDecision.reviewer_role)
    stage_counts = defaultdict(Counter)
    for row in db.scalars(select(RequestDecision).where(RequestDecision.id.in_(stage_latest))).all():
        if decision_is_current(db, row, *pair_map[row.request_id]):
            stage_counts[row.reviewer_role][row.outcome] += 1
    groups = {}
    for record, flow in pairs:
        result = current_result(db, record, flow)
        support = decision_support(result, record.text)
        human = latest.get(record.id)
        missing = json_loads(human.missing_topics_json, []) if human else support["missing_topics"]
        excess = json_loads(human.excess_topics_json, []) if human else []
        for topic in missing:
            gaps[topic].add(record.id)
            if human and human.training_need_confirmed:
                confirmed_gaps[topic].add(record.id)
        for topic in excess:
            extras[topic].add(record.id)
            if human and human.training_need_confirmed:
                confirmed_extras[topic].add(record.id)
        if flow and flow.status == "RESOLVED":
            continue
        if support["action"] not in ("NEW_COURSE", "ENRICH_COURSE") and not missing:
            continue
        subcategory = human.actual_subcategory_id if human else result.get("classification", {}).get("subcategory_id", "OTHER.REVIEW")
        # Canonical intent groups explicit like-for-like requests, not broad categories.
        topic = record.topic or result.get("classification", {}).get("topic") or "Kapsam netleştirme"
        key = (subcategory, canonicalize(record.canonical_intent or topic))
        if key not in groups:
            groups[key] = {"topic": topic, "subcategory_id": subcategory, "request_count": 0, "confirmed_count": 0,
                           "request_ids": [], "missing_topics": [], "excess_topics": [],
                           "suggested_department": support["suggested_department"], "action": support["action"]}
        group = groups[key]
        group["request_ids"].append(record.id)
        group["request_count"] += 1
        group["confirmed_count"] += int(bool(human and human.training_need_confirmed))
        group["missing_topics"] = _topics(group["missing_topics"] + missing)
        group["excess_topics"] = _topics(group["excess_topics"] + excess)
    ranked = lambda data, confirmed: [{"topic": topic, "count": len(requests), "confirmed_count": len(confirmed[topic]), "request_ids": sorted(requests)}
                          for topic, requests in sorted(data.items(), key=lambda item: (-len(item[1]), item[0]))][:30]
    return {"summary": {"total_requests": len(ids), "reviewed_requests": reviewed, "pending_review": len(ids) - reviewed,
                        "decisions_total": total_history, "approved": counts["APPROVED"], "modified": counts["MODIFIED"], "rejected": counts["REJECTED"],
                        "agreement_percent": round(100 * counts["APPROVED"] / reviewed, 1) if reviewed else None,
                        "correction_percent": round(100 * (counts["MODIFIED"] + counts["REJECTED"]) / reviewed, 1) if reviewed else None},
            "repeated_needs": sorted((group for group in groups.values() if group["request_count"] >= 2), key=lambda group: -group["request_count"])[:30],
            "scope_gaps": ranked(gaps, confirmed_gaps), "excess_scope": ranked(extras, confirmed_extras),
            "by_role": [{"role": role, "reviewed_requests": sum(counts.values()), "approved": counts["APPROVED"],
                         "modified": counts["MODIFIED"], "rejected": counts["REJECTED"]} for role, counts in sorted(stage_counts.items())],
            "learning": {"mode": "validated_feedback_retrieval", "model_weights_trained": False, "autonomous_decisions_enabled": False,
                         "explanation": "Her talebin son insan kararı rapora tek örnek olarak girer. Güncel PDF ile doğrulanan ders kararları yalnızca benzer niyetli arama sırasını etkiler; eşleşme yüzdesini artırmaz. Model ağırlıkları eğitilmez ve özerk karar verme etkin değildir."}}
