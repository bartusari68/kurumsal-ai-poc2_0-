"""Additive organizational positions and immutable requirement snapshots."""
from datetime import datetime
from sqlalchemy import Integer, String, Text, Boolean, ForeignKey, UniqueConstraint, CheckConstraint, event, DDL
from sqlalchemy.orm import Mapped, mapped_column
from .database import Base
from .time_policy import UTCDateTime, utc_now

class PositionProfile(Base):
    __tablename__ = 'position_profiles'
    __table_args__ = (CheckConstraint("status IN ('ACTIVE','INACTIVE')"), CheckConstraint('version > 0'))
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(180))
    normalized_name: Mapped[str] = mapped_column(String(240), unique=True)
    code: Mapped[str | None] = mapped_column(String(64), nullable=True, unique=True)
    description: Mapped[str] = mapped_column(Text, default='')
    organization: Mapped[str | None] = mapped_column(String(255), nullable=True)
    unit: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(12), default='ACTIVE')
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_by: Mapped[int] = mapped_column(ForeignKey('portal_users.id'))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utc_now)

class PositionRevision(Base):
    __tablename__ = 'position_revisions'
    __table_args__ = (UniqueConstraint('profile_id', 'version'),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    profile_id: Mapped[int] = mapped_column(ForeignKey('position_profiles.id'), index=True)
    version: Mapped[int] = mapped_column(Integer)
    snapshot_json: Mapped[str] = mapped_column(Text)
    sealed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_by: Mapped[int] = mapped_column(ForeignKey('portal_users.id'))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utc_now)

class PositionRequirement(Base):
    __tablename__ = 'position_requirements'
    __table_args__ = (UniqueConstraint('revision_id', 'skill_id'), CheckConstraint("requirement_type IN ('REQUIRED','RECOMMENDED')"))
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    revision_id: Mapped[int] = mapped_column(ForeignKey('position_revisions.id'), index=True)
    skill_id: Mapped[int] = mapped_column(ForeignKey('skills.id'), index=True)
    skill_name: Mapped[str] = mapped_column(String(160))
    requirement_type: Mapped[str] = mapped_column(String(16))
    rationale: Mapped[str] = mapped_column(Text, default='')
    created_by: Mapped[int] = mapped_column(ForeignKey('portal_users.id'))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utc_now)

class UserPosition(Base):
    __tablename__ = 'user_positions'
    user_id: Mapped[int] = mapped_column(ForeignKey('portal_users.id'), primary_key=True)
    profile_id: Mapped[int | None] = mapped_column(ForeignKey('position_profiles.id'), nullable=True, index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    assigned_by: Mapped[int] = mapped_column(ForeignKey('portal_users.id'))
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utc_now)

class PositionAudit(Base):
    __tablename__ = 'position_audit'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    profile_id: Mapped[int | None] = mapped_column(ForeignKey('position_profiles.id'), nullable=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey('portal_users.id'), nullable=True)
    actor_id: Mapped[int] = mapped_column(ForeignKey('portal_users.id'))
    actor_name: Mapped[str] = mapped_column(String(160))
    action: Mapped[str] = mapped_column(String(32))
    details_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utc_now)

class RequestPositionSource(Base):
    __tablename__ = 'request_position_sources'
    request_id: Mapped[int] = mapped_column(ForeignKey('requests.id'), primary_key=True)
    requirement_id: Mapped[int] = mapped_column(ForeignKey('position_requirements.id'), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('portal_users.id'))
    source_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utc_now)

GUARDS = [
    *[f"CREATE TRIGGER IF NOT EXISTS {table}_no_delete BEFORE DELETE ON {table} BEGIN SELECT RAISE(ABORT,'Position history cannot be deleted'); END" for table in ('position_profiles','position_revisions','position_requirements','user_positions','position_audit','request_position_sources')],
    *[f"CREATE TRIGGER IF NOT EXISTS {table}_immutable BEFORE UPDATE ON {table} BEGIN SELECT RAISE(ABORT,'Position snapshot is immutable'); END" for table in ('position_requirements','position_audit','request_position_sources')],
    "CREATE TRIGGER IF NOT EXISTS position_revision_seal BEFORE UPDATE ON position_revisions WHEN OLD.sealed=1 OR NEW.sealed<>1 OR NEW.snapshot_json IS NOT OLD.snapshot_json OR NEW.profile_id<>OLD.profile_id OR NEW.version<>OLD.version OR NEW.created_by<>OLD.created_by OR NEW.created_at IS NOT OLD.created_at BEGIN SELECT RAISE(ABORT,'Position revision is immutable'); END",
    "CREATE TRIGGER IF NOT EXISTS position_requirement_sealed BEFORE INSERT ON position_requirements WHEN (SELECT sealed FROM position_revisions WHERE id=NEW.revision_id) IS NOT 0 BEGIN SELECT RAISE(ABORT,'Create a new requirement revision'); END",
]
for statement in GUARDS:
    event.listen(Base.metadata, 'after_create', DDL(statement).execute_if(dialect='sqlite'))

def install(bind):
    if bind.dialect.name == 'sqlite':
        with bind.begin() as connection:
            for statement in GUARDS: connection.exec_driver_sql(statement)
