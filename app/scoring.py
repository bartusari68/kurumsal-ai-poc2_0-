"""Transparent suitability index, not a calibrated probability of correctness."""
import math
from .utils import compact_text

VERSION = "fit-v2-grounded-70-20-10"
POLICY_VERSION = "coverage-v2-40-95"
MIN_SUITABLE_PERCENT = 40
NEAR_COMPLETE_PERCENT = 95


def unit(value):
    try:
        number = float(value)
        return max(0.0, min(1.0, number)) if math.isfinite(number) else 0.0
    except (TypeError, ValueError):
        return 0.0


def retrieval_rank(semantic, rerank, feedback=0):
    # Feedback can reorder candidates, but is never included in user fit percentages.
    return min(1.0, .8 * unit(rerank) + .2 * unit(semantic) + min(.05, unit(feedback)))


def course_fit(requirements, assessment, evidence):
    valid = {str(item["evidence_id"]): item for item in evidence}
    claimed = {}
    for item in assessment.get("needs", []) if isinstance(assessment.get("needs"), list) else []:
        if not isinstance(item, list) or len(item) != 3 or not isinstance(item[2], list):
            continue
        identifier, status, references = item
        identifier = str(identifier)
        if identifier in claimed:  # Duplicates cannot inflate coverage.
            continue
        references = list(dict.fromkeys(str(ref) for ref in references if str(ref) in valid))
        state = str(status).upper()
        if state not in ("FULL", "PARTIAL") or not references:
            state, references = "NONE", []
        claimed[identifier] = (state, references)
    outcomes, used, relevance, similarity = [], set(), [], []
    weights = {"FULL": 1.0, "PARTIAL": .5, "NONE": 0.0}
    for requirement in requirements:
        state, refs = claimed.get(requirement["id"], ("NONE", []))
        used.update(refs)
        outcomes.append({"id": requirement["id"], "label": requirement["label"], "status": state})
        # A strong chunk for one need cannot supply relevance points for other,
        # unmet needs. All three components use the same requirement denominator.
        relevance.append(weights[state] * max((unit(valid[ref].get("rerank_score")) for ref in refs), default=0.0))
        similarity.append(weights[state] * max((unit(valid[ref].get("semantic_score")) for ref in refs), default=0.0))
    coverage = sum(weights[item["status"]] for item in outcomes) / len(outcomes) if outcomes else 0.0
    rerank = sum(relevance) / len(outcomes) if outcomes else 0.0
    semantic = sum(similarity) / len(outcomes) if outcomes else 0.0
    points = {"need_coverage": round(70 * coverage, 1), "content_relevance": round(20 * rerank, 1), "semantic_similarity": round(10 * semantic, 1)}
    percent = round(sum(points.values())) if coverage else 0
    return {"version": VERSION, "percent": percent, "label": "Tama yakın uyum" if percent >= NEAR_COMPLETE_PERCENT else "Kısmi uyum" if percent > MIN_SUITABLE_PERCENT else "Sınırlı uyum" if percent else "Destekleyici içerik bulunamadı",
            "requirements": outcomes, "components": points, "weights": {"need_coverage": 70, "content_relevance": 20, "semantic_similarity": 10},
            "grounding_verified": assessment.get("grounding_verified") is True,
            "explanation": "Her ihtiyaç ayrı değerlendirilir: ihtiyaç kapsamı %70 + içerik ilgisi %20 + anlamsal benzerlik %10. Karşılanmayan ihtiyaçlar tüm bileşenlerde sıfırdır. Bu oran doğruluk olasılığı değildir.",
            "summary": compact_text(str(assessment.get("summary") or "İçerik ihtiyacınızın bir bölümünü destekliyor."), 360) if coverage else "Bu ders için ihtiyacınızı destekleyen yeterli içerik doğrulanamadı.",
            "topics": [compact_text(str(t), 80) for t in assessment.get("topics", [])[:5]] if coverage and isinstance(assessment.get("topics"), list) else []}


def coverage_policy(top_fit, requirements, *, evidence_strength="DUSUK", need_type="EGITIM", risk_level="NORMAL"):
    percent = top_fit["percent"] if top_fit else 0
    unmet = [item["label"] for item in (top_fit["requirements"] if top_fit else requirements)
             if item.get("status") != "FULL"]
    complete = bool(top_fit and not unmet and top_fit.get("grounding_verified") and evidence_strength == "GUCLU")
    status = "VAR" if percent >= NEAR_COMPLETE_PERCENT and complete else "KISMEN_VAR" if percent > MIN_SUITABLE_PERCENT else "YOK"
    training = need_type in {"EGITIM", "KARMA"}
    urgent = need_type == "KRITIK_ICERIK" or risk_level == "KRITIK"
    validation_gaps = []
    if top_fit and not unmet and status != "VAR":
        validation_gaps.append("İhtiyaç başlıkları için kanıt var; tam yeterlilik kararı için içerik derinliği ve uygulama kazanımları uzman tarafından doğrulanmalı.")
    if status == "YOK":
        reason = "Taranan güncel ders içeriklerinde %40 eşiğini aşan yeterli eşleşme doğrulanamadı. İhtiyaç analiz ekibine değerlendirme kaydı oluşturuldu."
        action = "YENI_DERS_IHTIYACI" if training else "EGITIM_DISI_COZUM"
    elif status == "VAR":
        reason = "Talebin tüm ihtiyaçları PDF kanıtlarıyla destekleniyor ve ders uyumu %95 veya üzerinde. Nihai karar insan değerlendirmesiyle onaylanacak."
        action = "DERS_ONAYI"
    else:
        reason = "Mevcut dersler ihtiyacın bir bölümünü destekliyor. Eksik kapsam ve içerik yeterliliği analiz ekibince değerlendirilerek ilgili birime iletilecek."
        action = "ICERIK_ZENGINLESTIRME" if training else "EGITIM_DISI_COZUM"
    if urgent:
        action = "ACIL_INCELEME"
        reason = "Talep kritik içerik veya prosedür riski taşıyor. Kapsam eşleşmesi tek başına uygulama kararı değildir; öncelikli uzman incelemesi gerekiyor."
    return {"status": status, "fit_percent": percent, "reason": reason, "missing_topics": unmet,
            "validation_gaps": validation_gaps, "needs_new_course": status == "YOK" and training and not urgent,
            "next_action": action, "policy_version": POLICY_VERSION,
            "thresholds": {"minimum_suitable_exclusive": MIN_SUITABLE_PERCENT, "near_complete": NEAR_COMPLETE_PERCENT}}
