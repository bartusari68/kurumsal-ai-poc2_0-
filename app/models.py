from __future__ import annotations
from .time_policy import utc_now, as_utc, utc_stamp

from datetime import datetime

from sqlalchemy import Boolean, Index, Float, ForeignKey, Integer, String, Text, UniqueConstraint, CheckConstraint, DDL, event, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base
from .time_policy import UTCDateTime as DateTime
from .training_models import TrainingSession, Enrollment, TrainingEvent, TrainingNotification
from .evaluation_models import LearningEvaluation, EvaluationEvent, EvaluationDelivery
from .skill_models import SkillGroup, Skill, SkillTerm, CourseSkillMapping, RequestSkillNeed, SkillEvidence, SkillAudit
from .portfolio_models import PortfolioItem, PortfolioEvent, PortfolioHandoff, PortfolioLink
from .position_models import PositionProfile, PositionRevision, PositionRequirement, UserPosition, PositionAudit, RequestPositionSource
from .governance_models import CourseGovernance, GovernanceReview, GovernanceEvent, MandatoryPolicy, LearningRequirement
from .identity_models import (Identity, ExternalIdentityLink, OrganizationUnit, OrganizationMembership,
    UserManagerRelation, SyncRun, IdentityConflict, ExternalRoleMapping, ExternalPositionMapping,
    IntegrationAuditEvent, NotificationPreference)
from .communication_models import CommunicationDelivery

# Domain aliases keep the additive models discoverable from the long-standing
# ``app.models`` import path used by integrations and tests.
ExternalIdentity = ExternalIdentityLink
IdentityLink = ExternalIdentityLink
OrganizationMembershipHistory = OrganizationMembership
SyncConflict = IdentityConflict
RoleMapping = ExternalRoleMapping
PositionMapping = ExternalPositionMapping


class OperationOutbox(Base):
    __tablename__ = 'operation_outbox'
    event_id: Mapped[int] = mapped_column(ForeignKey('request_events.id'), primary_key=True)
    payload_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    retry_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    event: Mapped['RequestEvent'] = relationship()


class Notification(Base):
    __tablename__ = 'notifications'
    __table_args__ = (UniqueConstraint('source_event_id', 'recipient_id', name='uq_notification_event_recipient'),
                     Index('ix_notifications_recipient_read_id', 'recipient_id', 'read_at', 'id'),
                     Index('ix_notifications_recipient_id', 'recipient_id', 'id'))
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    recipient_id: Mapped[int] = mapped_column(ForeignKey('portal_users.id'))
    request_id: Mapped[int] = mapped_column(ForeignKey('requests.id'), index=True)
    source_event_id: Mapped[int] = mapped_column(ForeignKey('request_events.id'))
    type: Mapped[str] = mapped_column(String(48))
    title: Mapped[str] = mapped_column(String(180))
    message: Mapped[str] = mapped_column(String(500))
    importance: Mapped[str] = mapped_column(String(16), default='normal')
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    read_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class Delegation(Base):
    __tablename__ = 'delegations'
    __table_args__ = (CheckConstraint('delegator_id != delegate_id AND end_at > start_at', name='ck_delegation_range'),
                     Index('ix_delegation_recipient_window', 'delegate_id', 'active', 'start_at', 'end_at'))
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    delegator_id: Mapped[int] = mapped_column(ForeignKey('portal_users.id'), index=True)
    delegate_id: Mapped[int] = mapped_column(ForeignKey('portal_users.id'))
    start_at: Mapped[datetime] = mapped_column(DateTime)
    end_at: Mapped[datetime] = mapped_column(DateTime)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by: Mapped[int] = mapped_column(ForeignKey('portal_users.id'))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    reason: Mapped[str] = mapped_column(String(600), default='')


class DelegationAudit(Base):
    __tablename__ = 'delegation_audit'
    __table_args__ = (UniqueConstraint('delegation_id', 'action', name='uq_delegation_lifecycle'),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    delegation_id: Mapped[int] = mapped_column(ForeignKey('delegations.id'), index=True)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey('portal_users.id'), nullable=True)
    action: Mapped[str] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    details_json: Mapped[str] = mapped_column(Text, default='{}')


class EscalationRecord(Base):
    __tablename__ = 'escalations'
    __table_args__ = (UniqueConstraint('request_id', 'policy_key', 'stage_started_at', name='uq_escalation_stage'),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    request_id: Mapped[int] = mapped_column(ForeignKey('requests.id'), index=True)
    policy_key: Mapped[str] = mapped_column(String(64))
    stage_started_at: Mapped[datetime] = mapped_column(DateTime)
    event_id: Mapped[int] = mapped_column(ForeignKey('request_events.id'))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class DevelopmentItem(Base):
    __tablename__ = 'development_items'
    __table_args__ = (
        CheckConstraint("work_type IN ('NEW_COURSE','COURSE_ENRICHMENT')"),
        CheckConstraint("state IN ('DRAFT','ANALYSIS','DESIGN','REVIEW','READY','CANCELLED')"),
        CheckConstraint("work_type != 'COURSE_ENRICHMENT' OR source_course_id IS NOT NULL"),
        Index('uq_development_active_need', 'source_request_id', 'work_type', unique=True,
              sqlite_where=text("state NOT IN ('READY','CANCELLED')")),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_request_id: Mapped[int] = mapped_column(ForeignKey('requests.id'), index=True)
    work_type: Mapped[str] = mapped_column(String(32))
    title: Mapped[str] = mapped_column(String(255))
    summary: Mapped[str] = mapped_column(Text)
    responsible_unit: Mapped[str] = mapped_column(String(40), index=True)
    assignee_id: Mapped[int | None] = mapped_column(ForeignKey('portal_users.id'), nullable=True)
    state: Mapped[str] = mapped_column(String(20), default='DRAFT', index=True)
    target_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    source_course_id: Mapped[int | None] = mapped_column(ForeignKey('courses.id'), nullable=True)
    source_course_hash: Mapped[str] = mapped_column(String(64), default='')
    catalog_course_id: Mapped[int | None] = mapped_column(ForeignKey('courses.id'), nullable=True)
    source_context_json: Mapped[str] = mapped_column(Text, default='{}')
    brief_json: Mapped[str] = mapped_column(Text, default='{}')
    version: Mapped[int] = mapped_column(Integer, default=1)
    content_revision: Mapped[int] = mapped_column(Integer, default=0)
    created_by: Mapped[int] = mapped_column(ForeignKey('portal_users.id'))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    stage_started_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class DevelopmentOutcome(Base):
    __tablename__ = 'development_outcomes'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    item_id: Mapped[int] = mapped_column(ForeignKey('development_items.id'), index=True)
    position: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class DevelopmentModule(Base):
    __tablename__ = 'development_modules'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    item_id: Mapped[int] = mapped_column(ForeignKey('development_items.id'), index=True)
    position: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text, default='')


class DevelopmentTopic(Base):
    __tablename__ = 'development_topics'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    module_id: Mapped[int] = mapped_column(ForeignKey('development_modules.id'), index=True)
    position: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text, default='')


class DevelopmentEvent(Base):
    __tablename__ = 'development_events'
    __table_args__ = (UniqueConstraint('item_id', 'version', name='uq_development_event_version'),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    item_id: Mapped[int] = mapped_column(ForeignKey('development_items.id'), index=True)
    request_event_id: Mapped[int | None] = mapped_column(ForeignKey('request_events.id'), nullable=True, unique=True)
    actor_id: Mapped[int] = mapped_column(ForeignKey('portal_users.id'))
    actor_name: Mapped[str] = mapped_column(String(160))
    action: Mapped[str] = mapped_column(String(32))
    from_state: Mapped[str | None] = mapped_column(String(20), nullable=True)
    to_state: Mapped[str] = mapped_column(String(20))
    version: Mapped[int] = mapped_column(Integer)
    content_revision: Mapped[int] = mapped_column(Integer)
    note: Mapped[str] = mapped_column(Text, default='')
    snapshot_json: Mapped[str] = mapped_column(Text, default='{}')
    delegation_json: Mapped[str] = mapped_column(Text, default='{}')
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class CatalogMigration(Base):
    __tablename__ = 'catalog_migrations'
    name: Mapped[str] = mapped_column(String(80), primary_key=True)
    applied_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class CourseCatalog(Base):
    __tablename__ = 'course_catalog'
    course_id: Mapped[int] = mapped_column(ForeignKey('courses.id'), primary_key=True)
    current_version_id: Mapped[int | None] = mapped_column(ForeignKey('course_versions.id'), nullable=True)
    responsible_unit: Mapped[str | None] = mapped_column(String(40), nullable=True)
    revision: Mapped[int] = mapped_column(Integer, default=1)


class CourseVersion(Base):
    __tablename__ = 'course_versions'
    __table_args__ = (UniqueConstraint('course_id', 'version_number'),
        CheckConstraint("state IN ('DRAFT','READY_FOR_PUBLISH','PUBLISHED','ARCHIVED')"),
        CheckConstraint("state NOT IN ('PUBLISHED','ARCHIVED') OR course_id IS NOT NULL"),
        Index('uq_course_current_publication', 'course_id', unique=True, sqlite_where=text("state = 'PUBLISHED'")))
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    course_id: Mapped[int | None] = mapped_column(ForeignKey('courses.id'), nullable=True, index=True)
    version_number: Mapped[int] = mapped_column(Integer)
    base_version_id: Mapped[int | None] = mapped_column(ForeignKey('course_versions.id'), nullable=True)
    proposed_code: Mapped[str] = mapped_column(String(64), default='')
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text, default='')
    outcomes_json: Mapped[str] = mapped_column(Text, default='[]')
    outline_json: Mapped[str] = mapped_column(Text, default='[]')
    source_development_id: Mapped[int | None] = mapped_column(ForeignKey('development_items.id'), nullable=True, unique=True)
    source_review_id: Mapped[int | None] = mapped_column(ForeignKey('development_events.id'), nullable=True)
    source_ready_id: Mapped[int | None] = mapped_column(ForeignKey('development_events.id'), nullable=True)
    source_request_id: Mapped[int | None] = mapped_column(ForeignKey('requests.id'), nullable=True)
    source_analysis_id: Mapped[int | None] = mapped_column(ForeignKey('analysis_runs.id'), nullable=True)
    source_decision_id: Mapped[int | None] = mapped_column(ForeignKey('request_decisions.id'), nullable=True)
    state: Mapped[str] = mapped_column(String(24), default='DRAFT', index=True)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    legacy: Mapped[bool] = mapped_column(Boolean, default=False)
    created_by: Mapped[int | None] = mapped_column(ForeignKey('portal_users.id'), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    published_by: Mapped[int | None] = mapped_column(ForeignKey('portal_users.id'), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class CourseVersionDocument(Base):
    __tablename__ = 'course_version_documents'
    version_id: Mapped[int] = mapped_column(ForeignKey('course_versions.id'), primary_key=True)
    source_path: Mapped[str] = mapped_column(String(1024))
    content_hash: Mapped[str] = mapped_column(String(64))
    linked_by: Mapped[int | None] = mapped_column(ForeignKey('portal_users.id'), nullable=True)
    linked_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class PublicationEvent(Base):
    __tablename__ = 'publication_events'
    __table_args__ = (UniqueConstraint('version_id', 'revision'),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    version_id: Mapped[int] = mapped_column(ForeignKey('course_versions.id'), index=True)
    revision: Mapped[int] = mapped_column(Integer)
    action: Mapped[str] = mapped_column(String(32))
    actor_id: Mapped[int | None] = mapped_column(ForeignKey('portal_users.id'), nullable=True)
    actor_name: Mapped[str] = mapped_column(String(160))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    request_event_id: Mapped[int | None] = mapped_column(ForeignKey('request_events.id'), nullable=True, unique=True)
    details_json: Mapped[str] = mapped_column(Text, default='{}')


class Course(Base):
    __tablename__ = "courses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text, default="")
    pdf_path: Mapped[str] = mapped_column(String(1024))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    chunks: Mapped[list["CourseChunk"]] = relationship(back_populates="course", cascade="all, delete-orphan")


class CourseChunk(Base):
    __tablename__ = "course_chunks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), index=True)
    page_number: Mapped[int] = mapped_column(Integer, index=True)
    chunk_index: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text)
    embedding_json: Mapped[str] = mapped_column(Text)
    embedding_provider: Mapped[str] = mapped_column(String(255), index=True)

    course: Mapped[Course] = relationship(back_populates="chunks")


class DocumentIndex(Base):
    """Derived search state; missing sources retain their historical course IDs."""
    __tablename__ = "document_index"

    path_key: Mapped[str] = mapped_column(String(1024), primary_key=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id"), unique=True, index=True)
    content_hash: Mapped[str] = mapped_column(String(64), default="")
    embedding_provider: Mapped[str] = mapped_column(String(255), default="")
    pipeline_version: Mapped[str] = mapped_column(String(64), default="")
    status: Mapped[str] = mapped_column(String(32), default="pending")
    error: Mapped[str] = mapped_column(Text, default="")
    page_count: Mapped[int] = mapped_column(Integer, default=0)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    indexed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class RequestRecord(Base):
    __tablename__ = "requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    text: Mapped[str] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(128), default="")
    topic: Mapped[str] = mapped_column(String(255), default="")
    intent: Mapped[str] = mapped_column(String(255), default="")
    canonical_intent: Mapped[str] = mapped_column(String(255), index=True, default="")
    coverage: Mapped[str] = mapped_column(String(32), default="BELIRSIZ")
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    ai_reason: Mapped[str] = mapped_column(Text, default="")
    missing_topics_json: Mapped[str] = mapped_column(Text, default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    matches: Mapped[list["RequestMatch"]] = relationship(back_populates="request", cascade="all, delete-orphan")


class RequestMatch(Base):
    __tablename__ = "request_matches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    request_id: Mapped[int] = mapped_column(ForeignKey("requests.id", ondelete="CASCADE"), index=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), index=True)
    score: Mapped[float] = mapped_column(Float)
    evidence_json: Mapped[str] = mapped_column(Text, default="[]")

    request: Mapped[RequestRecord] = relationship(back_populates="matches")
    course: Mapped[Course] = relationship()


class AnalysisRun(Base):
    __tablename__ = "analysis_runs"
    __table_args__ = (UniqueConstraint("request_id", "sequence", name="uq_analysis_sequence"),
                     UniqueConstraint("request_id", "idempotency_key", name="uq_analysis_operation"),
                     CheckConstraint("(status IN ('PENDING','PROCESSING') AND active_request_id IS NOT NULL AND active_request_id = request_id) OR (status IN ('COMPLETED','FAILED') AND active_request_id IS NULL)", name="ck_analysis_active_state"))
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    request_id: Mapped[int] = mapped_column(ForeignKey("requests.id"), index=True)
    sequence: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), index=True)
    # Nullable unique reservation enforces one active run, including across processes.
    active_request_id: Mapped[int | None] = mapped_column(ForeignKey("requests.id"), unique=True, nullable=True)
    trigger: Mapped[str] = mapped_column(String(32))
    idempotency_key: Mapped[str | None] = mapped_column(String(80), nullable=True)
    input_json: Mapped[str] = mapped_column(Text)
    result_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    canonical_intent: Mapped[str] = mapped_column(String(255), default="", index=True)
    error_code: Mapped[str | None] = mapped_column(String(48), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    triggered_by: Mapped[int | None] = mapped_column(ForeignKey("portal_users.id"), nullable=True)
    retry_of: Mapped[int | None] = mapped_column(ForeignKey("analysis_runs.id"), nullable=True)
    lease_token: Mapped[str | None] = mapped_column(String(64), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)


class RequestSubmission(Base):
    __tablename__ = "request_submissions"
    __table_args__ = (UniqueConstraint("owner_hash", "idempotency_key", name="uq_request_submission"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    request_id: Mapped[int] = mapped_column(ForeignKey("requests.id"), unique=True)
    owner_hash: Mapped[str] = mapped_column(String(64))
    idempotency_key: Mapped[str] = mapped_column(String(80))
    text_hash: Mapped[str] = mapped_column(String(64))


class DecisionAnalysisLink(Base):
    __tablename__ = "decision_analysis_links"
    decision_id: Mapped[int] = mapped_column(ForeignKey("request_decisions.id"), primary_key=True)
    analysis_run_id: Mapped[int] = mapped_column(ForeignKey("analysis_runs.id"), index=True)


class HumanReview(Base):
    __tablename__ = "human_reviews"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    request_id: Mapped[int] = mapped_column(ForeignKey("requests.id", ondelete="CASCADE"), index=True)
    approved: Mapped[bool] = mapped_column(Boolean)
    correct_course_id: Mapped[int | None] = mapped_column(ForeignKey("courses.id"), nullable=True)
    comment: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class LearnedMapping(Base):
    __tablename__ = "learned_mappings"
    __table_args__ = (UniqueConstraint("canonical_intent", "course_id", name="uq_intent_course"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    canonical_intent: Mapped[str] = mapped_column(String(255), index=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id"), index=True)
    approved_count: Mapped[int] = mapped_column(Integer, default=1)
    weight: Mapped[float] = mapped_column(Float, default=0.12)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now)

    course: Mapped[Course] = relationship()


class PortalSession(Base):
    __tablename__ = "portal_sessions"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    admin_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class RequestWorkflow(Base):
    """Additive migration: legacy request rows stay unchanged and admin-only."""
    __tablename__ = "request_workflows"
    request_id: Mapped[int] = mapped_column(ForeignKey("requests.id"), primary_key=True)
    owner_hash: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(32), default="IN_REVIEW", index=True)
    public_note: Mapped[str] = mapped_column(Text, default="")
    result_json: Mapped[str] = mapped_column(Text, default="{}")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    version: Mapped[int] = mapped_column(Integer, default=1)


class RequestEvent(Base):
    __tablename__ = "request_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    request_id: Mapped[int] = mapped_column(ForeignKey("requests.id"), index=True)
    status: Mapped[str] = mapped_column(String(32))
    actor: Mapped[str] = mapped_column(String(32))
    note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class PortalUser(Base):
    __tablename__ = "portal_users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(160))
    role: Mapped[str] = mapped_column(String(40), index=True)
    password_salt: Mapped[str] = mapped_column(String(32))
    password_hash: Mapped[str] = mapped_column(String(64))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class RequestEventIdentity(Base):
    """Additive actor snapshots; legacy role-only events remain honestly unattributed."""
    __tablename__ = "request_event_identities"
    event_id: Mapped[int] = mapped_column(ForeignKey("request_events.id"), primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("portal_users.id"), nullable=True)
    display_name: Mapped[str] = mapped_column(String(160))
    role: Mapped[str] = mapped_column(String(40))
    event: Mapped[RequestEvent] = relationship()


class UserOrganization(Base):
    """Optional HR metadata. Employee origin is never a solution routing target."""
    __tablename__ = "user_organizations"
    user_id: Mapped[int] = mapped_column(ForeignKey("portal_users.id"), primary_key=True)
    organization: Mapped[str | None] = mapped_column(String(255), nullable=True)
    directorate: Mapped[str | None] = mapped_column(String(255), nullable=True)
    unit: Mapped[str | None] = mapped_column(String(255), nullable=True)
    chiefdom: Mapped[str | None] = mapped_column(String(255), nullable=True)
    manager_user_id: Mapped[int | None] = mapped_column(ForeignKey("portal_users.id"), nullable=True)
    external_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source: Mapped[str | None] = mapped_column(String(80), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class RequestAssignment(Base):
    __tablename__ = "request_assignments"
    request_id: Mapped[int] = mapped_column(ForeignKey("requests.id"), primary_key=True)
    responsible_scope: Mapped[str] = mapped_column(String(40))
    assignee_id: Mapped[int | None] = mapped_column(ForeignKey("portal_users.id"), nullable=True, index=True)
    assigned_by: Mapped[int] = mapped_column(ForeignKey("portal_users.id"))
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class RequestSolutionPlan(Base):
    __tablename__ = "request_solution_plans"
    request_id: Mapped[int] = mapped_column(ForeignKey("requests.id"), primary_key=True)
    summary: Mapped[str] = mapped_column(Text)
    responsible_unit: Mapped[str] = mapped_column(String(40))
    assignee_id: Mapped[int | None] = mapped_column(ForeignKey("portal_users.id"), nullable=True)
    target_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    state: Mapped[str] = mapped_column(String(24), default="planned")
    created_by: Mapped[int] = mapped_column(ForeignKey("portal_users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class RequestEventAction(Base):
    """Append-only action details, without rewriting any previous event rows."""
    __tablename__ = "request_event_actions"
    event_id: Mapped[int] = mapped_column(ForeignKey("request_events.id"), primary_key=True)
    action: Mapped[str] = mapped_column(String(40))
    from_status: Mapped[str] = mapped_column(String(32))
    to_status: Mapped[str] = mapped_column(String(32))
    details_json: Mapped[str] = mapped_column(Text, default="{}")
    event: Mapped[RequestEvent] = relationship()


class AccountSession(Base):
    __tablename__ = "account_sessions"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("portal_users.id"), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime)


class RequestReferral(Base):
    __tablename__ = "request_referrals"
    request_id: Mapped[int] = mapped_column(ForeignKey("requests.id"), primary_key=True)
    department: Mapped[str] = mapped_column(String(40), index=True)
    analysis_summary: Mapped[str] = mapped_column(Text)
    training_need_confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    analyst_id: Mapped[int] = mapped_column(ForeignKey("portal_users.id"))
    completed_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)


class RequestDecision(Base):
    """Append-only human judgements; AI observations and reviewer identity stay frozen."""
    __tablename__ = "request_decisions"
    __table_args__ = (UniqueConstraint("request_id", "request_version", name="uq_decision_request_version"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    request_id: Mapped[int] = mapped_column(ForeignKey("requests.id"), index=True)
    reviewer_id: Mapped[int] = mapped_column(ForeignKey("portal_users.id"), index=True)
    reviewer_name: Mapped[str] = mapped_column(String(160))
    reviewer_role: Mapped[str] = mapped_column(String(40))
    request_version: Mapped[int] = mapped_column(Integer)
    outcome: Mapped[str] = mapped_column(String(16), index=True)
    reason: Mapped[str] = mapped_column(Text)
    original_ai_json: Mapped[str] = mapped_column(Text)
    actual_subcategory_id: Mapped[str] = mapped_column(String(80), default="OTHER.REVIEW")
    actual_department: Mapped[str | None] = mapped_column(String(40), nullable=True)
    actual_course_id: Mapped[int | None] = mapped_column(ForeignKey("courses.id"), nullable=True)
    course_source_hash: Mapped[str] = mapped_column(String(64), default="")
    training_need_confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    missing_topics_json: Mapped[str] = mapped_column(Text, default="[]")
    excess_topics_json: Mapped[str] = mapped_column(Text, default="[]")
    changed_fields_json: Mapped[str] = mapped_column(Text, default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


@event.listens_for(RequestDecision, "before_update")
@event.listens_for(RequestDecision, "before_delete")
@event.listens_for(RequestEvent, "before_update")
@event.listens_for(RequestEvent, "before_delete")
@event.listens_for(RequestEventIdentity, "before_update")
@event.listens_for(RequestEventIdentity, "before_delete")
@event.listens_for(RequestEventAction, "before_update")
@event.listens_for(RequestEventAction, "before_delete")
@event.listens_for(DecisionAnalysisLink, "before_update")
@event.listens_for(DecisionAnalysisLink, "before_delete")
@event.listens_for(RequestSubmission, "before_update")
@event.listens_for(RequestSubmission, "before_delete")
def _preserve_decision_history(mapper, connection, target):
    raise ValueError("Karar geçmişi değiştirilemez; yeni bir değerlendirme ekleyin.")


# The existing SQLite deployment also protects history from bulk SQL updates.
for _history_model in (RequestDecision, RequestEvent, RequestEventIdentity, RequestEventAction, DecisionAnalysisLink, RequestSubmission, DelegationAudit, EscalationRecord, DevelopmentEvent):
    for _operation in ("UPDATE", "DELETE"):
        event.listen(_history_model.__table__, "after_create", DDL(
            "CREATE TRIGGER " + _history_model.__tablename__ + "_no_" + _operation.lower() +
            " BEFORE " + _operation + " ON " + _history_model.__tablename__ + " "
            "BEGIN SELECT RAISE(ABORT, 'Decision history is append-only'); END"
        ).execute_if(dialect="sqlite"))


def install_decision_guards(bind):
    """Idempotent additive guard install also covers tables from earlier app starts."""
    if bind.dialect.name != "sqlite":
        return
    with bind.begin() as connection:
        for model in (RequestDecision, RequestEvent, RequestEventIdentity, RequestEventAction, DecisionAnalysisLink, RequestSubmission, DelegationAudit, EscalationRecord, DevelopmentEvent):
            for operation in ("UPDATE", "DELETE"):
                connection.exec_driver_sql(
                    "CREATE TRIGGER IF NOT EXISTS " + model.__tablename__ + "_no_" + operation.lower() +
                    " BEFORE " + operation + " ON " + model.__tablename__ + " "
                    "BEGIN SELECT RAISE(ABORT, 'Decision history is append-only'); END")


def install_analysis_guards(bind):
    if bind.dialect.name != "sqlite":
        return
    statements = [
        "CREATE TRIGGER IF NOT EXISTS original_request_immutable BEFORE UPDATE OF text ON requests WHEN NEW.text IS NOT OLD.text BEGIN SELECT RAISE(ABORT, 'Original request is immutable'); END",
        "CREATE TRIGGER IF NOT EXISTS analysis_no_delete BEFORE DELETE ON analysis_runs BEGIN SELECT RAISE(ABORT, 'Analysis history is immutable'); END",
        "CREATE TRIGGER IF NOT EXISTS analysis_terminal_immutable BEFORE UPDATE ON analysis_runs WHEN OLD.status IN ('COMPLETED','FAILED') BEGIN SELECT RAISE(ABORT, 'Completed analysis is immutable'); END",
        "CREATE TRIGGER IF NOT EXISTS analysis_input_immutable BEFORE UPDATE ON analysis_runs WHEN NEW.input_json IS NOT OLD.input_json OR NEW.request_id IS NOT OLD.request_id OR NEW.sequence IS NOT OLD.sequence OR NEW.trigger IS NOT OLD.trigger OR NEW.triggered_by IS NOT OLD.triggered_by OR NEW.retry_of IS NOT OLD.retry_of OR NEW.created_at IS NOT OLD.created_at OR NEW.idempotency_key IS NOT OLD.idempotency_key BEGIN SELECT RAISE(ABORT, 'Analysis input is immutable'); END",
        "CREATE TRIGGER IF NOT EXISTS analysis_state_guard BEFORE UPDATE ON analysis_runs WHEN NOT ((OLD.status = 'PENDING' AND NEW.status IN ('PROCESSING','FAILED')) OR (OLD.status = 'PROCESSING' AND NEW.status IN ('PROCESSING','COMPLETED','FAILED'))) BEGIN SELECT RAISE(ABORT, 'Invalid analysis transition'); END",
    ]
    with bind.begin() as connection:
        for statement in statements:
            connection.exec_driver_sql(statement)
