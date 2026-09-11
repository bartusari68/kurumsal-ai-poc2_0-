"""Learning-governance services.

The service keeps catalogue/version records immutable and stores lifecycle,
review and policy decisions in additive tables.  All mutating operations are
manager-only; employee endpoints are limited to that employee's requirements.
"""
from datetime import timedelta
import json
from fastapi import HTTPException
from sqlalchemy import select, func, and_, or_, update

from .governance_models import (CourseGovernance, GovernanceReview, GovernanceEvent,
    MandatoryPolicy, LearningRequirement)
from .models import (Course, CourseVersion, CourseCatalog, DevelopmentItem, PortalUser, UserOrganization,
                      RequestRecord, RequestWorkflow)
from .training_models import TrainingSession, Enrollment
from .position_models import PositionProfile, PositionRevision, UserPosition
from .portfolio_models import PortfolioItem
from .skill_models import CourseSkillMapping
from .time_policy import utc_now, utc_stamp
from .utils import json_dumps, json_loads
from . import governance_policy as policy


def _course(db, course_id):
    row = db.get(Course, course_id)
    if not row:
        raise HTTPException(404, "Ders bulunamadı.")
    catalog = db.get(CourseCatalog, course_id)
    current = db.get(CourseVersion, catalog.current_version_id) if catalog and catalog.current_version_id else None
    return row, catalog, current


def _row(db, course_id, create=False, actor=None):
    row = db.get(CourseGovernance, course_id)
    if row or not create:
        return row
    row = CourseGovernance(course_id=course_id)
    db.add(row)
    db.flush()
    _event(db, course_id, actor, "GOVERNANCE_INITIALIZED", to_state="ACTIVE") if actor else None
    return row


def _event(db, course_id, actor, action, review_id=None, policy_id=None, requirement_id=None,
           from_state=None, to_state=None, reason="", snapshot=None):
    last = db.scalar(select(func.max(GovernanceEvent.version)).where(GovernanceEvent.course_id == course_id)) or 0
    db.add(GovernanceEvent(course_id=course_id, review_id=review_id, policy_id=policy_id,
        requirement_id=requirement_id, action=action, actor_id=getattr(actor, "user_id", None),
        actor_name=getattr(actor, "display_name", "system"), from_state=from_state,
        to_state=to_state, reason=reason, snapshot_json=json_dumps(snapshot or {}), version=last + 1))


def _effective_status(row):
    if not row:
        return "CURRENT"
    if row.governance_status == "CURRENT" and row.review_enabled and row.next_review_at and row.next_review_at <= utc_now():
        return "REVIEW_DUE"
    return row.governance_status


def course_summary(db, course, actor=None):
    catalog = db.get(CourseCatalog, course.id)
    current = db.get(CourseVersion, catalog.current_version_id) if catalog and catalog.current_version_id else None
    row = _row(db, course.id)
    owner = db.get(PortalUser, row.owner_user_id) if row and row.owner_user_id else None
    reviews = list(db.scalars(select(GovernanceReview).where(GovernanceReview.course_id == course.id).order_by(GovernanceReview.id.desc()).limit(10)))
    active_policy_count = db.scalar(select(func.count()).select_from(MandatoryPolicy).where(
        MandatoryPolicy.course_id == course.id, MandatoryPolicy.status == "ACTIVE")) or 0
    return {
        "course_id": course.id,
        "version": row.version if row else 1,
        "lifecycle_state": row.lifecycle_state if row else "ACTIVE",
        "lifecycle_label": policy.LIFECYCLE[row.lifecycle_state] if row else policy.LIFECYCLE["ACTIVE"],
        "governance_status": _effective_status(row),
        "governance_status_label": policy.GOVERNANCE_STATUSES[_effective_status(row)],
        "owner_unit": row.owner_unit if row else None,
        "owner_user": {"id": owner.id, "display_name": owner.display_name} if owner else None,
        "review_policy": {
            "enabled": bool(row and row.review_enabled),
            "interval_days": row.review_interval_days if row else None,
            "scope": row.review_scope if row else None,
            "next_review_at": utc_stamp(row.next_review_at) if row else None,
            "last_reviewed_at": utc_stamp(row.last_reviewed_at) if row else None,
        },
        "rationale": row.rationale if row else "",
        "active_mandatory_policy_count": active_policy_count,
        "current_version_id": current.id if current else None,
        "reviews": [{"id": item.id, "status": item.status, "decision": item.decision,
                      "decision_label": policy.REVIEW_DECISIONS.get(item.decision) if item.decision else None,
                      "reason": item.reason, "started_at": utc_stamp(item.started_at),
                      "decided_at": utc_stamp(item.decided_at)} for item in reviews],
        "history": [{"action": e.action, "from_state": e.from_state, "to_state": e.to_state,
                      "actor": e.actor_name, "reason": e.reason, "at": utc_stamp(e.created_at)}
                    for e in db.scalars(select(GovernanceEvent).where(GovernanceEvent.course_id == course.id).order_by(GovernanceEvent.id.desc()).limit(25))],
    }


def update_course(db, actor, course_id, data):
    policy.require_manager(actor)
    course, _, _ = _course(db, course_id)
    row = _row(db, course_id, create=True, actor=actor)
    expected = data.get("expected_version")
    if expected is not None and expected != row.version:
        raise HTTPException(409, "Yönetişim kaydı güncellendi; güncel kaydı açın.")
    owner_id = data.get("owner_user_id")
    if owner_id is not None:
        user = db.get(PortalUser, owner_id)
        if not user or not user.active:
            raise HTTPException(422, "Sahip olarak yalnızca aktif bir kullanıcı seçilebilir.")
    before = course_summary(db, course, actor)
    for key in ("owner_unit", "owner_user_id", "review_scope", "rationale"):
        if key in data:
            setattr(row, key, data[key])
    if "review_enabled" in data:
        row.review_enabled = bool(data["review_enabled"])
    if "review_interval_days" in data:
        value = data["review_interval_days"]
        if value is not None and (not isinstance(value, int) or value <= 0):
            raise HTTPException(422, "İnceleme aralığı pozitif gün sayısı olmalıdır.")
        row.review_interval_days = value
        if value and not row.next_review_at:
            row.next_review_at = utc_now() + timedelta(days=value)
        if value is None:
            row.next_review_at = None
    if "next_review_at" in data:
        row.next_review_at = data["next_review_at"]
    row.version += 1
    row.updated_at = utc_now()
    _event(db, course_id, actor, "GOVERNANCE_UPDATED", from_state=before["governance_status"],
           to_state=_effective_status(row), snapshot=data)
    db.commit()
    return course_summary(db, course, actor)


def start_review(db, actor, course_id, reason=""):
    policy.require_manager(actor)
    course, catalog, current = _course(db, course_id)
    row = _row(db, course_id, create=True, actor=actor)
    active = db.scalar(select(GovernanceReview).where(GovernanceReview.course_id == course_id,
        GovernanceReview.status == "UNDER_REVIEW"))
    if active:
        return review_detail(db, active)
    snapshot = {"course_id": course.id, "code": course.code, "name": course.name,
                "description": course.description, "current_version_id": current.id if current else None,
                "version_number": current.version_number if current else None,
                "title": current.title if current else course.name,
                "captured_at": utc_stamp(utc_now())}
    review = GovernanceReview(course_id=course_id, current_version_id=current.id if current else None,
        reason=(reason or "").strip(), snapshot_json=json_dumps(snapshot), actor_id=actor.user_id)
    db.add(review)
    row.governance_status = "UNDER_REVIEW"; row.version += 1; row.updated_at = utc_now()
    db.flush(); _event(db, course_id, actor, "REVIEW_STARTED", review_id=review.id,
                       from_state="CURRENT", to_state="UNDER_REVIEW", reason=reason, snapshot=snapshot)
    db.commit()
    return review_detail(db, review)


def review_detail(db, review):
    return {"id": review.id, "course_id": review.course_id, "status": review.status,
            "decision": review.decision, "decision_label": policy.REVIEW_DECISIONS.get(review.decision) if review.decision else None,
            "reason": review.reason, "snapshot": json_loads(review.snapshot_json, {}),
            "started_at": utc_stamp(review.started_at), "decided_at": utc_stamp(review.decided_at)}


def decide_review(db, actor, review_id, decision, reason=""):
    policy.require_manager(actor)
    review = db.get(GovernanceReview, review_id)
    if not review:
        raise HTTPException(404, "İnceleme bulunamadı.")
    if review.status != "UNDER_REVIEW":
        raise HTTPException(409, "Bu inceleme zaten sonuçlandırıldı.")
    if decision not in policy.REVIEW_DECISIONS:
        raise HTTPException(422, "Geçersiz inceleme kararı.")
    if len((reason or "").strip()) < 10:
        raise HTTPException(422, "İnceleme gerekçesi en az 10 karakter olmalıdır.")
    course, _, _ = _course(db, review.course_id)
    row = _row(db, review.course_id, create=True, actor=actor)
    review.status, review.decision, review.reason, review.decided_at = "DECIDED", decision, reason.strip(), utc_now()
    row.governance_status = "CURRENT"; row.last_reviewed_at = utc_now(); row.last_reviewed_by = actor.user_id
    if row.review_enabled and row.review_interval_days:
        row.next_review_at = utc_now() + timedelta(days=row.review_interval_days)
    row.version += 1; row.updated_at = utc_now()
    db.flush(); _event(db, review.course_id, actor, "REVIEW_DECIDED", review_id=review.id,
                       from_state="UNDER_REVIEW", to_state=decision, reason=reason,
                       snapshot=json_loads(review.snapshot_json, {}))
    db.commit()
    return review_detail(db, review)


def handoff_review(db, actor, review_id, reason):
    """Explicitly hand an update-required review into the existing enrichment flow.

    A review is not allowed to invent a request or synthetic employee context.
    It can only reuse a real request already attached to the published version;
    the normal development service then owns duplicate protection and audit.
    """
    policy.require_manager(actor)
    if len((reason or "").strip()) < 10:
        raise HTTPException(422, "Geliştirme devri gerekçesi en az 10 karakter olmalıdır.")
    review = db.get(GovernanceReview, review_id)
    if not review or review.status != "DECIDED" or review.decision != "UPDATE_REQUIRED":
        raise HTTPException(422, "Yalnızca güncelleme kararı verilmiş inceleme geliştirmeye devredilebilir.")
    course, catalog, current = _course(db, review.course_id)
    source_request_id = current.source_request_id if current else None
    if not source_request_id and current and current.source_development_id:
        source = db.get(DevelopmentItem, current.source_development_id)
        source_request_id = source.source_request_id if source else None
    if not source_request_id:
        raise HTTPException(422, "Bu ders sürümünde mevcut geliştirme talebi kaynağı bulunmuyor; yeni talep açmadan otomatik devir yapılamaz.")
    flow = db.get(RequestWorkflow, source_request_id)
    record = db.get(RequestRecord, source_request_id)
    if not flow or not record:
        raise HTTPException(422, "Dersin bağlı olduğu kaynak talep artık geçerli değil.")
    from . import development
    draft = development.source_draft(db, record, flow)
    if not draft or draft.get("work_type") != "COURSE_ENRICHMENT":
        raise HTTPException(422, "Mevcut talep güncel bir COURSE_ENRICHMENT akışına uygun değil.")
    recipient = db.scalar(select(PortalUser).where(PortalUser.active.is_(True), PortalUser.role == draft["responsible_unit"]).order_by(PortalUser.id))
    if not recipient:
        raise HTTPException(422, "İlgili eğitim tasarım biriminde aktif alıcı bulunamadı.")
    existing = db.scalar(select(DevelopmentItem).where(DevelopmentItem.source_request_id == source_request_id,
        DevelopmentItem.work_type == "COURSE_ENRICHMENT", DevelopmentItem.state.not_in(("READY", "CANCELLED"))))
    if existing:
        return {"review_id": review.id, "development": development.detail(db, existing, actor),
                "department": draft["responsible_unit"], "duplicate": True}
    from .portal_auth import Principal
    from .schemas import DevelopmentCreate
    target = Principal(recipient.id, recipient.username, recipient.display_name, recipient.role)
    result = development.create(db, target, DevelopmentCreate(source_request_id=source_request_id,
        expected_request_version=flow.version, work_type="COURSE_ENRICHMENT", source_course_id=course.id))
    _event(db, course.id, actor, "REVIEW_HANDED_OFF", review_id=review.id, to_state="COURSE_ENRICHMENT",
           reason=reason, snapshot={"development_id": result.get("id"), "source_request_id": source_request_id})
    db.commit()
    return {"review_id": review.id, "development": result, "department": draft["responsible_unit"]}


def retirement_check(db, actor, course_id):
    policy.require_manager(actor)
    course, catalog, current = _course(db, course_id)
    blockers, warnings = [], []
    if db.scalar(select(TrainingSession.id).join(CourseVersion, CourseVersion.id == TrainingSession.course_version_id).where(
        CourseVersion.course_id == course_id, TrainingSession.status == "SCHEDULED", TrainingSession.start_at > utc_now())):
        blockers.append("Gelecekte planlanmış bir eğitim oturumu var.")
    if db.scalar(select(DevelopmentItem.id).where(DevelopmentItem.source_course_id == course_id,
        DevelopmentItem.state.not_in(("READY", "CANCELLED")))):
        blockers.append("Aktif bir ders geliştirme çalışması var.")
    if db.scalar(select(CourseVersion.id).where(CourseVersion.course_id == course_id,
        CourseVersion.state.in_(("DRAFT", "READY_FOR_PUBLISH")))):
        blockers.append("Yayın bekleyen veya taslak ders sürümü var.")
    if db.scalar(select(MandatoryPolicy.id).where(MandatoryPolicy.course_id == course_id, MandatoryPolicy.status == "ACTIVE")):
        blockers.append("Aktif zorunlu eğitim politikası var.")
    skill_ids = set(db.scalars(select(CourseSkillMapping.skill_id).join(CourseVersion, CourseVersion.id == CourseSkillMapping.course_version_id).where(CourseVersion.course_id == course_id)))
    if skill_ids and db.scalar(select(PortfolioItem.id).where(PortfolioItem.skill_id.in_(skill_ids), PortfolioItem.state != "CLOSED")):
        warnings.append("Bu dersin yetkinlikleriyle ilişkili kapanmamış portföy kararı var.")
    for skill_id in skill_ids:
        other = db.scalar(select(CourseSkillMapping.id).join(CourseVersion, CourseVersion.id == CourseSkillMapping.course_version_id).join(CourseCatalog, CourseCatalog.current_version_id == CourseVersion.id).where(
            CourseSkillMapping.skill_id == skill_id, CourseVersion.course_id != course_id, CourseVersion.state == "PUBLISHED"))
        if not other:
            warnings.append("Bir yetkinlik için aktif yayımlanmış tek ders bu kayıt olabilir.")
            break
    row = _row(db, course_id)
    return {"course_id": course_id, "lifecycle_state": row.lifecycle_state if row else "ACTIVE",
            "blockers": blockers, "warnings": warnings, "can_retire": not blockers,
            "requires_warning_ack": bool(warnings)}


def retire(db, actor, course_id, reason, acknowledge_warnings=False):
    policy.require_manager(actor)
    if len((reason or "").strip()) < 10:
        raise HTTPException(422, "Emeklilik gerekçesi en az 10 karakter olmalıdır.")
    check = retirement_check(db, actor, course_id)
    if check["blockers"]:
        raise HTTPException(409, {"message": "Ders emekliye ayrılamaz.", "blockers": check["blockers"], "warnings": check["warnings"]})
    if check["warnings"] and not acknowledge_warnings:
        raise HTTPException(409, {"message": "Uyarıları onaylamadan ders emekliye ayrılamaz.", "warnings": check["warnings"]})
    course, _, _ = _course(db, course_id); row = _row(db, course_id, create=True, actor=actor)
    if row.lifecycle_state == "RETIRED":
        return course_summary(db, course, actor)
    before = row.lifecycle_state; row.lifecycle_state = "RETIRED"; row.version += 1; row.updated_at = utc_now()
    db.flush(); _event(db, course_id, actor, "COURSE_RETIRED", from_state=before, to_state="RETIRED", reason=reason)
    db.commit(); return course_summary(db, course, actor)


def restore(db, actor, course_id, reason):
    policy.require_manager(actor)
    if len((reason or "").strip()) < 10:
        raise HTTPException(422, "Geri alma gerekçesi en az 10 karakter olmalıdır.")
    course, _, _ = _course(db, course_id); row = _row(db, course_id, create=True, actor=actor)
    if row.lifecycle_state == "ACTIVE": return course_summary(db, course, actor)
    row.lifecycle_state = "ACTIVE"; row.version += 1; row.updated_at = utc_now()
    db.flush(); _event(db, course_id, actor, "COURSE_RESTORED", from_state="RETIRED", to_state="ACTIVE", reason=reason)
    db.commit(); return course_summary(db, course, actor)


def policy_data(db, row):
    course = db.get(Course, row.course_id); profile = db.get(PositionProfile, row.position_profile_id)
    version = db.get(CourseVersion, row.course_version_id) if row.course_version_id else None
    return {"id": row.id, "policy_key": row.policy_key, "version": row.version, "status": row.status,
            "status_label": policy.POLICY_STATUSES[row.status], "position_profile_id": row.position_profile_id,
            "position_profile": profile.name if profile else None, "course_id": row.course_id,
            "course": {"code": course.code, "name": course.name} if course else None,
            "course_version_id": row.course_version_id, "course_version_number": version.version_number if version else None,
            "organization": row.organization, "unit": row.unit, "effective_from": utc_stamp(row.effective_from),
            "effective_until": utc_stamp(row.effective_until), "recurrence_days": row.recurrence_days,
            "version_semantics": row.version_semantics, "rationale": row.rationale,
            "created_at": utc_stamp(row.created_at)}


def list_policies(db, actor, include_inactive=False):
    policy.require_read(actor)
    stmt = select(MandatoryPolicy).order_by(MandatoryPolicy.policy_key, MandatoryPolicy.version.desc())
    if not include_inactive: stmt = stmt.where(MandatoryPolicy.status == "ACTIVE")
    return {"items": [policy_data(db, row) for row in db.scalars(stmt)], "meaning": "Politika sürümleri korunur; değişiklik yeni sürüm olarak kaydedilir."}


def create_policy(db, actor, data):
    policy.require_manager(actor)
    profile = db.get(PositionProfile, data.get("position_profile_id")); course, catalog, current = _course(db, data.get("course_id"))
    lifecycle = db.get(CourseGovernance, course.id)
    if lifecycle and lifecycle.lifecycle_state == "RETIRED":
        raise HTTPException(422, "Emekliye ayrılmış ders için aktif zorunlu politika oluşturulamaz.")
    if not profile or profile.status != "ACTIVE": raise HTTPException(422, "Aktif bir pozisyon profili seçilmelidir.")
    if not current or current.state != "PUBLISHED": raise HTTPException(422, "Politika için yayımlanmış güncel ders gerekir.")
    semantics = data.get("version_semantics", "ANY_CURRENT_VERSION")
    if data.get("effective_until") and data.get("effective_from") and data["effective_until"] <= data["effective_from"]:
        raise HTTPException(422, "Politikanın bitiş zamanı başlangıçtan sonra olmalıdır.")
    selected = data.get("course_version_id")
    if semantics == "SPECIFIC_VERSION":
        version = db.get(CourseVersion, selected) if selected else None
        if not version or version.course_id != course.id or version.state not in ("PUBLISHED", "ARCHIVED"):
            raise HTTPException(422, "Belirli sürüm politikasında dersin geçerli bir sürümü seçilmelidir.")
    key = (data.get("policy_key") or f"PROFILE-{profile.id}-COURSE-{course.id}").strip()
    latest = db.scalar(select(func.max(MandatoryPolicy.version)).where(MandatoryPolicy.policy_key == key)) or 0
    previous = db.scalar(select(MandatoryPolicy).where(MandatoryPolicy.policy_key == key, MandatoryPolicy.status == "ACTIVE"))
    if previous: previous.status = "INACTIVE"
    row = MandatoryPolicy(policy_key=key, version=latest + 1, position_profile_id=profile.id, course_id=course.id,
        course_version_id=selected if semantics == "SPECIFIC_VERSION" else current.id,
        organization=data.get("organization"), unit=data.get("unit"), effective_from=data.get("effective_from") or utc_now(),
        effective_until=data.get("effective_until"), recurrence_days=data.get("recurrence_days"),
        version_semantics=semantics, rationale=(data.get("rationale") or "").strip(), created_by=actor.user_id)
    db.add(row); db.flush(); _event(db, course.id, actor, "POLICY_VERSION_CREATED", policy_id=row.id, to_state="ACTIVE", reason=row.rationale)
    db.commit(); return policy_data(db, row)


def inactivate_policy(db, actor, policy_id, reason):
    policy.require_manager(actor)
    row = db.get(MandatoryPolicy, policy_id)
    if not row: raise HTTPException(404, "Zorunlu eğitim politikası bulunamadı.")
    if len((reason or "").strip()) < 10: raise HTTPException(422, "Politika gerekçesi en az 10 karakter olmalıdır.")
    if row.status == "INACTIVE": return policy_data(db, row)
    row.status = "INACTIVE"; db.flush(); _event(db, row.course_id, actor, "POLICY_INACTIVATED", policy_id=row.id, from_state="ACTIVE", to_state="INACTIVE", reason=reason)
    db.commit(); return policy_data(db, row)


def revise_policy(db, actor, policy_id, data):
    policy.require_manager(actor)
    current = db.get(MandatoryPolicy, policy_id)
    if not current:
        raise HTTPException(404, "Zorunlu eğitim politikası bulunamadı.")
    if current.status != "ACTIVE":
        raise HTTPException(409, "Pasif politika sürümü yeniden düzenlenemez; yeni bir politika anahtarı oluşturun.")
    payload = {"policy_key": current.policy_key, "position_profile_id": current.position_profile_id,
               "course_id": current.course_id, "course_version_id": current.course_version_id,
               "organization": current.organization, "unit": current.unit,
               "effective_from": current.effective_from, "effective_until": current.effective_until,
               "recurrence_days": current.recurrence_days, "version_semantics": current.version_semantics,
               "rationale": current.rationale}
    payload.update({key: value for key, value in data.items() if value is not None})
    return create_policy(db, actor, payload)


def _active_policies_for_user(db, user_id):
    link = db.get(UserPosition, user_id)
    if not link or not link.profile_id: return [], None
    profile = db.get(PositionProfile, link.profile_id)
    if not profile or profile.status != "ACTIVE": return [], link
    now = utc_now()
    rows = list(db.scalars(select(MandatoryPolicy).where(MandatoryPolicy.position_profile_id == profile.id,
        MandatoryPolicy.status == "ACTIVE", MandatoryPolicy.effective_from <= now,
        or_(MandatoryPolicy.effective_until.is_(None), MandatoryPolicy.effective_until > now))))
    organization = db.get(UserOrganization, user_id)
    rows = [row for row in rows if (not row.organization or organization and row.organization == organization.organization)
            and (not row.unit or organization and row.unit == organization.unit)]
    return rows, link


def sync_requirements(db, user_id):
    rows, link = _active_policies_for_user(db, user_id)
    if not link or not link.profile_id: return []
    out = []
    for pol in rows:
        existing = db.scalar(select(LearningRequirement).where(LearningRequirement.user_id == user_id,
            LearningRequirement.policy_id == pol.id, LearningRequirement.policy_version == pol.version))
        if not existing:
            existing = LearningRequirement(user_id=user_id, policy_id=pol.id, policy_version=pol.version,
                course_id=pol.course_id, course_version_id=pol.course_version_id, source_profile_id=link.profile_id,
                source_profile_version=link.version, due_at=(utc_now() + timedelta(days=pol.recurrence_days)) if pol.recurrence_days else None)
            db.add(existing); db.flush(); _event(db, pol.course_id, None, "REQUIREMENT_CREATED", policy_id=pol.id,
                                                  requirement_id=existing.id, to_state="PENDING", reason="Zorunlu eğitim politikası")
        _sync_one(db, existing)
        out.append(existing)
    db.commit()
    return out


def _sync_one(db, req):
    if req.status in ("WAIVED",): return
    match = select(Enrollment, TrainingSession).join(TrainingSession, TrainingSession.id == Enrollment.session_id).join(
        CourseVersion, CourseVersion.id == TrainingSession.course_version_id).where(
        Enrollment.user_id == req.user_id, Enrollment.status == "ENROLLED", Enrollment.completion == "COMPLETED",
        TrainingSession.status != "CANCELLED", CourseVersion.course_id == req.course_id)
    if req.course_version_id:
        match = match.where(CourseVersion.id == req.course_version_id)
    pair = db.execute(match.order_by(Enrollment.completed_at.desc())).first()
    old = req.status
    if pair:
        enrollment, _ = pair; req.status, req.enrollment_id, req.completed_at = "FULFILLED", enrollment.id, enrollment.completed_at
    elif req.due_at and req.due_at <= utc_now():
        req.status, req.enrollment_id, req.completed_at = "EXPIRED", None, None
    else:
        req.status, req.enrollment_id, req.completed_at = "PENDING", None, None
    req.updated_at = utc_now()
    if old != req.status: _event(db, req.course_id, None, "REQUIREMENT_STATUS_CHANGED", policy_id=req.policy_id,
                                  requirement_id=req.id, from_state=old, to_state=req.status)


def requirement_data(db, row):
    pol = db.get(MandatoryPolicy, row.policy_id); course = db.get(Course, row.course_id)
    return {"id": row.id, "status": row.status, "status_label": policy.REQUIREMENT_STATUSES[row.status],
            "policy_id": row.policy_id, "policy_version": row.policy_version, "policy_key": pol.policy_key if pol else None,
            "course_id": row.course_id, "course": {"code": course.code, "name": course.name} if course else None,
            "course_version_id": row.course_version_id, "source_profile_id": row.source_profile_id,
            "source_profile_version": row.source_profile_version, "due_at": utc_stamp(row.due_at),
            "completed_at": utc_stamp(row.completed_at), "enrollment_id": row.enrollment_id,
            "waived_reason": row.waived_reason}


def my_requirements(db, actor):
    rows = sync_requirements(db, actor.user_id)
    return {"items": [requirement_data(db, row) for row in rows],
            "meaning": "Zorunluluk kaydı pozisyon ve politika sürümünün tarihsel kopyasıdır; otomatik kayıt yapılmaz."}


def all_requirements(db, actor, status=None):
    policy.require_read(actor)
    if actor.role != "NEEDS_ANALYST":
        raise HTTPException(403, "Öğrenme gereksinimi yönetimi ihtiyaç analizi yöneticisine aittir.")
    stmt = select(LearningRequirement).order_by(LearningRequirement.updated_at.desc())
    if status: stmt = stmt.where(LearningRequirement.status == status)
    rows = list(db.scalars(stmt))
    return {"items": [requirement_data(db, row) for row in rows], "total": len(rows),
            "suppressed": actor.role != "NEEDS_ANALYST", "meaning": "Kişisel gereksinim ayrıntıları yalnızca ihtiyaç analizi yöneticisine açıktır."}


def waive(db, actor, requirement_id, reason):
    policy.require_manager(actor)
    if len((reason or "").strip()) < 10: raise HTTPException(422, "Muafiyet gerekçesi en az 10 karakter olmalıdır.")
    row = db.get(LearningRequirement, requirement_id)
    if not row: raise HTTPException(404, "Öğrenme gereksinimi bulunamadı.")
    old = row.status; row.status, row.waived_reason, row.updated_at = "WAIVED", reason.strip(), utc_now()
    db.flush(); _event(db, row.course_id, actor, "REQUIREMENT_WAIVED", policy_id=row.policy_id, requirement_id=row.id,
                       from_state=old, to_state="WAIVED", reason=reason)
    db.commit(); return requirement_data(db, row)


def dashboard(db, actor):
    policy.require_read(actor)
    courses = list(db.scalars(select(Course).join(CourseCatalog, CourseCatalog.course_id == Course.id).order_by(Course.code)))
    due = [course_summary(db, c, actor) for c in courses if course_summary(db, c, actor)["governance_status"] in ("REVIEW_DUE", "UNDER_REVIEW")]
    requirements = all_requirements(db, actor)["items"] if actor.role == "NEEDS_ANALYST" else []
    return {"courses": due, "policies": list_policies(db, actor)["items"], "requirements": requirements,
            "counts": {"review_due": len(due), "active_policies": len(list_policies(db, actor)["items"]), "requirements": len(requirements)}}
