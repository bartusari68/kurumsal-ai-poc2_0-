"""Provider-independent identity and organization integration records.

The existing :class:`PortalUser` remains the application user and keeps its
current local-login behaviour.  These additive tables describe where an
identity came from, which organisation memberships were observed, and how an
external directory value was mapped.  No provider secret is stored here.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DDL,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    event,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base
from .time_policy import UTCDateTime, utc_now


IDENTITY_TYPES = ("LOCAL", "DIRECTORY", "SSO")
IDENTITY_STATUSES = ("ACTIVE", "INACTIVE")
SYNC_STATUSES = ("RUNNING", "COMPLETED", "FAILED")
CONFLICT_STATUSES = ("OPEN", "RESOLVED", "IGNORED")
APPLICATION_ROLES = (
    "EMPLOYEE",
    "NEEDS_ANALYST",
    "TECHNICAL_DESIGN",
    "ENGINEERING_DESIGN",
)


class Identity(Base):
    """A user's authentication source, deliberately separate from role."""

    __tablename__ = "identities"
    __table_args__ = (
        CheckConstraint("identity_type IN ('LOCAL','DIRECTORY','SSO')"),
        CheckConstraint("status IN ('ACTIVE','INACTIVE')"),
        UniqueConstraint("user_id", "identity_type", "provider", name="uq_identity_user_type_provider"),
        Index("ix_identity_user_status", "user_id", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("portal_users.id"), index=True)
    identity_type: Mapped[str] = mapped_column(String(16))
    provider: Mapped[str] = mapped_column(String(80), default="local")
    status: Mapped[str] = mapped_column(String(16), default="ACTIVE", index=True)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utc_now)
    last_authenticated_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)


class ExternalIdentityLink(Base):
    """A stable provider subject linked to at most one application user."""

    __tablename__ = "external_identity_links"
    __table_args__ = (
        CheckConstraint("status IN ('ACTIVE','INACTIVE')"),
        UniqueConstraint("provider", "external_subject_id", name="uq_external_identity_subject"),
        UniqueConstraint("user_id", "provider", name="uq_external_identity_user_provider"),
        Index("ix_external_identity_user_status", "user_id", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("portal_users.id"), index=True)
    provider: Mapped[str] = mapped_column(String(80), index=True)
    external_subject_id: Mapped[str] = mapped_column(String(255))
    username_snapshot: Mapped[str] = mapped_column(String(255), default="")
    email_snapshot: Mapped[str] = mapped_column(String(320), default="")
    status: Mapped[str] = mapped_column(String(16), default="ACTIVE", index=True)
    linked_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utc_now)
    last_seen_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    provider_metadata_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utc_now)


# Friendly name used by callers that prefer the wording from the phase brief.
IdentityLink = ExternalIdentityLink


class OrganizationUnit(Base):
    """Generic parent-child organisation node; levels are intentionally open."""

    __tablename__ = "organization_units"
    __table_args__ = (
        CheckConstraint("status IN ('ACTIVE','INACTIVE')"),
        CheckConstraint("parent_id IS NULL OR parent_id != id"),
        Index("ix_organization_unit_parent_status", "parent_id", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    external_id: Mapped[str | None] = mapped_column(String(255), nullable=True, unique=True)
    name: Mapped[str] = mapped_column(String(255))
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("organization_units.id"), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(16), default="ACTIVE", index=True)
    source: Mapped[str] = mapped_column(String(40), default="LOCAL")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utc_now)


class OrganizationMembership(Base):
    """Historical user-to-unit memberships with one current row per user."""

    __tablename__ = "organization_memberships"
    __table_args__ = (
        CheckConstraint("valid_to IS NULL OR valid_to >= valid_from"),
        Index(
            "uq_organization_membership_current",
            "user_id",
            unique=True,
            sqlite_where=text("current = 1"),
        ),
        Index("ix_organization_membership_user_dates", "user_id", "valid_from", "valid_to"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("portal_users.id"), index=True)
    organization_unit_id: Mapped[int] = mapped_column(ForeignKey("organization_units.id"), index=True)
    valid_from: Mapped[datetime] = mapped_column(UTCDateTime, default=utc_now)
    valid_to: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    source: Mapped[str] = mapped_column(String(40), default="LOCAL")
    is_current: Mapped[bool] = mapped_column("current", Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utc_now)


class UserManagerRelation(Base):
    """Optional reporting-line metadata; it never grants application access."""

    __tablename__ = "user_manager_relations"
    __table_args__ = (
        CheckConstraint("user_id != manager_user_id"),
        Index("uq_user_manager_current", "user_id", unique=True, sqlite_where=text("current = 1")),
        Index("ix_user_manager_manager", "manager_user_id", "current"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("portal_users.id"), index=True)
    manager_user_id: Mapped[int] = mapped_column(ForeignKey("portal_users.id"), index=True)
    valid_from: Mapped[datetime] = mapped_column(UTCDateTime, default=utc_now)
    valid_to: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    source: Mapped[str] = mapped_column(String(40), default="LOCAL")
    is_current: Mapped[bool] = mapped_column("current", Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utc_now)


class SyncRun(Base):
    """Durable summary of an external sync; dry-runs are never persisted."""

    __tablename__ = "identity_sync_runs"
    __table_args__ = (CheckConstraint("status IN ('RUNNING','COMPLETED','FAILED')"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    provider: Mapped[str] = mapped_column(String(80), index=True)
    started_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utc_now)
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="RUNNING", index=True)
    users_seen: Mapped[int] = mapped_column(Integer, default=0)
    created: Mapped[int] = mapped_column(Integer, default=0)
    updated: Mapped[int] = mapped_column(Integer, default=0)
    deactivated: Mapped[int] = mapped_column(Integer, default=0)
    organization_changes: Mapped[int] = mapped_column(Integer, default=0)
    errors_json: Mapped[str] = mapped_column(Text, default="[]")
    triggered_by: Mapped[int | None] = mapped_column(ForeignKey("portal_users.id"), nullable=True)
    dry_run: Mapped[bool] = mapped_column(Boolean, default=False, index=True)


class IdentityConflict(Base):
    """A deterministic, reviewable conflict instead of a silent overwrite."""

    __tablename__ = "identity_conflicts"
    __table_args__ = (
        CheckConstraint("status IN ('OPEN','RESOLVED','IGNORED')"),
        Index("uq_identity_conflict_open", "provider", "external_subject_id", "field", unique=True,
              sqlite_where=text("status = 'OPEN'")),
        Index("ix_identity_conflict_status", "status", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    provider: Mapped[str] = mapped_column(String(80), index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("portal_users.id"), nullable=True, index=True)
    external_subject_id: Mapped[str] = mapped_column(String(255), default="")
    field: Mapped[str] = mapped_column(String(80))
    local_value: Mapped[str] = mapped_column(Text, default="")
    external_value: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(16), default="OPEN", index=True)
    resolution: Mapped[str] = mapped_column(String(40), default="")
    resolved_by: Mapped[int | None] = mapped_column(ForeignKey("portal_users.id"), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utc_now)


class ExternalRoleMapping(Base):
    """Explicit external group/claim to existing application-role mapping."""

    __tablename__ = "external_role_mappings"
    __table_args__ = (
        CheckConstraint("application_role IN ('EMPLOYEE','NEEDS_ANALYST','TECHNICAL_DESIGN','ENGINEERING_DESIGN')"),
        UniqueConstraint("provider", "external_key", name="uq_external_role_mapping"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    provider: Mapped[str] = mapped_column(String(80), index=True)
    external_key: Mapped[str] = mapped_column(String(255))
    application_role: Mapped[str] = mapped_column(String(40))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("portal_users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utc_now)


class ExternalPositionMapping(Base):
    """Explicit external job key to an existing PositionProfile."""

    __tablename__ = "external_position_mappings"
    __table_args__ = (
        CheckConstraint("status IN ('MAPPED','PENDING')"),
        UniqueConstraint("provider", "external_position_key", name="uq_external_position_mapping"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    provider: Mapped[str] = mapped_column(String(80), index=True)
    external_position_key: Mapped[str] = mapped_column(String(255))
    position_profile_id: Mapped[int | None] = mapped_column(ForeignKey("position_profiles.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="PENDING", index=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("portal_users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utc_now)


class IntegrationAuditEvent(Base):
    """Meaningful integration changes, without unchanged-user event spam."""

    __tablename__ = "integration_audit_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    action: Mapped[str] = mapped_column(String(64), index=True)
    provider: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("portal_users.id"), nullable=True, index=True)
    sync_run_id: Mapped[int | None] = mapped_column(ForeignKey("identity_sync_runs.id"), nullable=True)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("portal_users.id"), nullable=True)
    details_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utc_now)


class NotificationPreference(Base):
    """Small opt-in preference record; no rows are fabricated during sync."""

    __tablename__ = "notification_preferences"
    __table_args__ = (CheckConstraint("in_app IN (0,1) AND email IN (0,1) AND teams IN (0,1)"),)

    user_id: Mapped[int] = mapped_column(ForeignKey("portal_users.id"), primary_key=True)
    in_app: Mapped[bool] = mapped_column(Boolean, default=True)
    email: Mapped[bool] = mapped_column(Boolean, default=False)
    teams: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utc_now)


GUARDS = (
    "CREATE TRIGGER IF NOT EXISTS integration_audit_no_update BEFORE UPDATE ON integration_audit_events BEGIN SELECT RAISE(ABORT,'Integration audit is append-only'); END",
    "CREATE TRIGGER IF NOT EXISTS integration_audit_no_delete BEFORE DELETE ON integration_audit_events BEGIN SELECT RAISE(ABORT,'Integration audit is append-only'); END",
)

for statement in GUARDS:
    event.listen(Base.metadata, "after_create", DDL(statement).execute_if(dialect="sqlite"))


def install(bind):
    """Install additive SQLite guards/indexes on an already-created database."""

    if bind.dialect.name != "sqlite":
        return
    with bind.begin() as connection:
        for statement in GUARDS:
            connection.exec_driver_sql(statement)
    for index in IdentityConflict.__table__.indexes:
        index.create(bind, checkfirst=True)


# Backwards-compatible aliases make the domain terminology easy to discover.
OrganizationMembershipHistory = OrganizationMembership
SyncConflict = IdentityConflict
RoleMapping = ExternalRoleMapping
PositionMapping = ExternalPositionMapping
