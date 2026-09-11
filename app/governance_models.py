"""Additive learning-governance records.

Governance is deliberately kept separate from the immutable catalogue/version
tables.  This lets legacy courses receive a conservative default (ACTIVE,
CURRENT, no owner) without changing or rewriting their publication history.
"""
from datetime import datetime
from sqlalchemy import Integer, String, Text, Boolean, ForeignKey, UniqueConstraint, CheckConstraint, Index, DDL, event, text
from sqlalchemy.orm import Mapped, mapped_column
from .database import Base
from .time_policy import UTCDateTime, utc_now


class CourseGovernance(Base):
    __tablename__ = "course_governance"
    __table_args__ = (
        CheckConstraint("governance_status IN ('CURRENT','REVIEW_DUE','UNDER_REVIEW')"),
        CheckConstraint("lifecycle_state IN ('ACTIVE','RETIRED')"),
        CheckConstraint("review_interval_days IS NULL OR review_interval_days > 0"),
        Index("ix_course_governance_lifecycle", "lifecycle_state"),
    )
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id"), primary_key=True)
    owner_unit: Mapped[str | None] = mapped_column(String(120), nullable=True)
    owner_user_id: Mapped[int | None] = mapped_column(ForeignKey("portal_users.id"), nullable=True)
    governance_status: Mapped[str] = mapped_column(String(20), default="CURRENT", index=True)
    review_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    review_interval_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    review_scope: Mapped[str | None] = mapped_column(String(500), nullable=True)
    next_review_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True, index=True)
    last_reviewed_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    last_reviewed_by: Mapped[int | None] = mapped_column(ForeignKey("portal_users.id"), nullable=True)
    lifecycle_state: Mapped[str] = mapped_column(String(12), default="ACTIVE", index=True)
    rationale: Mapped[str] = mapped_column(Text, default="")
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utc_now)


class GovernanceReview(Base):
    __tablename__ = "governance_reviews"
    __table_args__ = (CheckConstraint("status IN ('UNDER_REVIEW','DECIDED')"),
                      CheckConstraint("decision IS NULL OR decision IN ('KEEP_CURRENT','UPDATE_REQUIRED','RETIREMENT_REVIEW')"),
                      Index("ix_governance_reviews_course_status", "course_id", "status"))
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id"), index=True)
    current_version_id: Mapped[int | None] = mapped_column(ForeignKey("course_versions.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="UNDER_REVIEW")
    decision: Mapped[str | None] = mapped_column(String(32), nullable=True)
    reason: Mapped[str] = mapped_column(Text, default="")
    snapshot_json: Mapped[str] = mapped_column(Text, default="{}")
    actor_id: Mapped[int] = mapped_column(ForeignKey("portal_users.id"))
    started_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utc_now)
    decided_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1)


class GovernanceEvent(Base):
    __tablename__ = "governance_events"
    __table_args__ = (UniqueConstraint("course_id", "version", name="uq_governance_event_version"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id"), index=True)
    review_id: Mapped[int | None] = mapped_column(ForeignKey("governance_reviews.id"), nullable=True)
    policy_id: Mapped[int | None] = mapped_column(ForeignKey("mandatory_policies.id"), nullable=True)
    requirement_id: Mapped[int | None] = mapped_column(ForeignKey("learning_requirements.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(40))
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("portal_users.id"), nullable=True)
    actor_name: Mapped[str] = mapped_column(String(160), default="system")
    from_state: Mapped[str | None] = mapped_column(String(32), nullable=True)
    to_state: Mapped[str | None] = mapped_column(String(32), nullable=True)
    reason: Mapped[str] = mapped_column(Text, default="")
    snapshot_json: Mapped[str] = mapped_column(Text, default="{}")
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utc_now)


class MandatoryPolicy(Base):
    __tablename__ = "mandatory_policies"
    __table_args__ = (
        UniqueConstraint("policy_key", "version", name="uq_mandatory_policy_version"),
        CheckConstraint("status IN ('ACTIVE','INACTIVE')"),
        CheckConstraint("version_semantics IN ('ANY_CURRENT_VERSION','SPECIFIC_VERSION')"),
        CheckConstraint("course_id IS NOT NULL"),
        Index("ix_mandatory_policy_profile_active", "position_profile_id", "status"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    policy_key: Mapped[str] = mapped_column(String(120), index=True)
    version: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(12), default="ACTIVE", index=True)
    position_profile_id: Mapped[int] = mapped_column(ForeignKey("position_profiles.id"), index=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id"), index=True)
    course_version_id: Mapped[int | None] = mapped_column(ForeignKey("course_versions.id"), nullable=True)
    organization: Mapped[str | None] = mapped_column(String(255), nullable=True)
    unit: Mapped[str | None] = mapped_column(String(255), nullable=True)
    effective_from: Mapped[datetime] = mapped_column(UTCDateTime, default=utc_now)
    effective_until: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    recurrence_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    version_semantics: Mapped[str] = mapped_column(String(28), default="ANY_CURRENT_VERSION")
    rationale: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[int] = mapped_column(ForeignKey("portal_users.id"))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utc_now)


class LearningRequirement(Base):
    __tablename__ = "learning_requirements"
    __table_args__ = (
        UniqueConstraint("user_id", "policy_id", "policy_version", name="uq_learning_requirement_policy_user"),
        CheckConstraint("status IN ('PENDING','FULFILLED','WAIVED','EXPIRED')"),
        Index("ix_learning_requirement_user_status", "user_id", "status"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("portal_users.id"), index=True)
    policy_id: Mapped[int] = mapped_column(ForeignKey("mandatory_policies.id"), index=True)
    policy_version: Mapped[int] = mapped_column(Integer)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id"), index=True)
    course_version_id: Mapped[int | None] = mapped_column(ForeignKey("course_versions.id"), nullable=True)
    source_profile_id: Mapped[int] = mapped_column(ForeignKey("position_profiles.id"))
    source_profile_version: Mapped[int] = mapped_column(Integer)
    due_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="PENDING", index=True)
    enrollment_id: Mapped[int | None] = mapped_column(ForeignKey("training_enrollments.id"), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    waived_reason: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utc_now)


GUARDS = [
    *[f"CREATE TRIGGER IF NOT EXISTS governance_{table}_no_delete BEFORE DELETE ON {table} BEGIN SELECT RAISE(ABORT,'Governance history cannot be deleted'); END"
      for table in ("governance_reviews", "governance_events", "mandatory_policies", "learning_requirements")],
    *[f"CREATE TRIGGER IF NOT EXISTS governance_{table}_immutable BEFORE UPDATE ON {table} BEGIN SELECT RAISE(ABORT,'Governance history is append-only'); END"
      for table in ("governance_events",)],
    "CREATE TRIGGER IF NOT EXISTS governance_review_snapshot_immutable BEFORE UPDATE ON governance_reviews WHEN NEW.course_id<>OLD.course_id OR NEW.current_version_id IS NOT OLD.current_version_id OR NEW.snapshot_json IS NOT OLD.snapshot_json OR NEW.actor_id<>OLD.actor_id OR NEW.started_at IS NOT OLD.started_at BEGIN SELECT RAISE(ABORT,'Review snapshot is immutable'); END",
    "CREATE TRIGGER IF NOT EXISTS governance_no_retired_training BEFORE INSERT ON training_sessions WHEN EXISTS (SELECT 1 FROM course_versions v JOIN course_governance g ON g.course_id=v.course_id WHERE v.id=NEW.course_version_id AND g.lifecycle_state='RETIRED') BEGIN SELECT RAISE(ABORT,'Retired course cannot receive a new training session'); END",
]
for statement in GUARDS:
    event.listen(Base.metadata, "after_create", DDL(statement).execute_if(dialect="sqlite"))


def install(bind):
    if bind.dialect.name == "sqlite":
        with bind.begin() as connection:
            for statement in GUARDS:
                connection.exec_driver_sql(statement)
