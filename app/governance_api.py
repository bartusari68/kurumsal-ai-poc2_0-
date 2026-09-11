from fastapi import APIRouter, Depends, Query
from .database import get_db
from .development_api import session
from .portal_auth import require_employee
from .governance_schemas import (GovernanceUpdate, ReviewStart, ReviewDecision, ReviewHandoff, RetirementAction,
    RestoreAction, PolicyCreate, PolicyInactivate, RequirementWaive)
from .governance_schemas import PolicyRevision
from . import governance

router = APIRouter(prefix="/api/governance")


@router.get("")
def dashboard(actor=Depends(session), db=Depends(get_db)):
    return governance.dashboard(db, actor)


@router.get("/courses/{course_id}")
def course(course_id: int, actor=Depends(session), db=Depends(get_db)):
    from .models import Course
    row = db.get(Course, course_id)
    if not row:
        from fastapi import HTTPException
        raise HTTPException(404, "Ders bulunamadı.")
    if actor.role == "EMPLOYEE":
        from fastapi import HTTPException
        raise HTTPException(403, "Ders yönetişimi çalışan görünümünde değildir.")
    from . import governance_policy as policy
    policy.require_read(actor)
    return governance.course_summary(db, row, actor)


@router.patch("/courses/{course_id}")
def update(course_id: int, payload: GovernanceUpdate, actor=Depends(session), db=Depends(get_db)):
    return governance.update_course(db, actor, course_id, payload.model_dump(exclude_unset=True))


@router.post("/courses/{course_id}/reviews", status_code=201)
def start_review(course_id: int, payload: ReviewStart, actor=Depends(session), db=Depends(get_db)):
    return governance.start_review(db, actor, course_id, payload.reason)


@router.post("/reviews/{review_id}/decision")
def decision(review_id: int, payload: ReviewDecision, actor=Depends(session), db=Depends(get_db)):
    return governance.decide_review(db, actor, review_id, payload.decision, payload.reason)


@router.get("/reviews/{review_id}")
def review(review_id: int, actor=Depends(session), db=Depends(get_db)):
    from fastapi import HTTPException
    from . import governance_policy as policy
    policy.require_read(actor)
    row = db.get(governance.GovernanceReview, review_id)
    if not row:
        raise HTTPException(404, "İnceleme bulunamadı.")
    return governance.review_detail(db, row)


@router.post("/reviews/{review_id}/handoff", status_code=201)
def handoff(review_id: int, payload: ReviewHandoff, actor=Depends(session), db=Depends(get_db)):
    return governance.handoff_review(db, actor, review_id, payload.reason)


@router.get("/courses/{course_id}/retirement-check")
def retirement_check(course_id: int, actor=Depends(session), db=Depends(get_db)):
    return governance.retirement_check(db, actor, course_id)


@router.post("/courses/{course_id}/retire")
def retire(course_id: int, payload: RetirementAction, actor=Depends(session), db=Depends(get_db)):
    return governance.retire(db, actor, course_id, payload.reason, payload.acknowledge_warnings)


@router.post("/courses/{course_id}/restore")
def restore(course_id: int, payload: RestoreAction, actor=Depends(session), db=Depends(get_db)):
    return governance.restore(db, actor, course_id, payload.reason)


@router.get("/policies")
def policies(include_inactive: bool = Query(False), actor=Depends(session), db=Depends(get_db)):
    return governance.list_policies(db, actor, include_inactive)


@router.post("/policies", status_code=201)
def create_policy(payload: PolicyCreate, actor=Depends(session), db=Depends(get_db)):
    return governance.create_policy(db, actor, payload.model_dump())


@router.patch("/policies/{policy_id}")
def revise_policy(policy_id: int, payload: PolicyRevision, actor=Depends(session), db=Depends(get_db)):
    return governance.revise_policy(db, actor, policy_id, payload.model_dump(exclude_unset=True))


@router.post("/policies/{policy_id}/inactivate")
def inactivate_policy(policy_id: int, payload: PolicyInactivate, actor=Depends(session), db=Depends(get_db)):
    return governance.inactivate_policy(db, actor, policy_id, payload.reason)


@router.get("/requirements/mine")
def requirements_mine(actor=Depends(require_employee), db=Depends(get_db)):
    return governance.my_requirements(db, actor)


@router.get("/requirements")
def requirements(status: str | None = Query(None), actor=Depends(session), db=Depends(get_db)):
    return governance.all_requirements(db, actor, status)


@router.post("/requirements/{requirement_id}/waive")
def waive(requirement_id: int, payload: RequirementWaive, actor=Depends(session), db=Depends(get_db)):
    return governance.waive(db, actor, requirement_id, payload.reason)
