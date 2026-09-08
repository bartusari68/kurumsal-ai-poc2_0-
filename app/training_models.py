"""Additive training operations tables; no synthetic requests or trainer accounts."""
from datetime import datetime
from sqlalchemy import Integer, String, Text, ForeignKey, UniqueConstraint, CheckConstraint, Index, DDL, event
from sqlalchemy.orm import Mapped, mapped_column
from .database import Base
from .time_policy import UTCDateTime, utc_now


class TrainingSession(Base):
    __tablename__ = 'training_sessions'
    __table_args__ = (
        CheckConstraint("status IN ('DRAFT','SCHEDULED','IN_PROGRESS','COMPLETED','CANCELLED')"),
        CheckConstraint('capacity IS NULL OR capacity > 0'),
        CheckConstraint('end_at IS NULL OR start_at IS NULL OR end_at > start_at'),
        CheckConstraint("delivery_mode IN ('IN_PERSON','ONLINE','HYBRID')"),
        CheckConstraint('version > 0'),
        Index('ix_training_unit_status_start', 'responsible_unit', 'status', 'start_at'),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    course_version_id: Mapped[int] = mapped_column(ForeignKey('course_versions.id'), index=True)
    title: Mapped[str] = mapped_column(String(255))
    responsible_unit: Mapped[str] = mapped_column(String(40))
    coordinator_id: Mapped[int | None] = mapped_column(ForeignKey('portal_users.id'), nullable=True)
    trainer_user_id: Mapped[int | None] = mapped_column(ForeignKey('portal_users.id'), nullable=True)
    external_trainer: Mapped[str] = mapped_column(String(255), default='')
    start_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    end_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    capacity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    delivery_mode: Mapped[str] = mapped_column(String(20))
    location: Mapped[str] = mapped_column(String(500), default='')
    online_url: Mapped[str] = mapped_column(String(1000), default='')
    status: Mapped[str] = mapped_column(String(20), default='DRAFT', index=True)
    cancellation_reason: Mapped[str] = mapped_column(Text, default='')
    attendance_finalized_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_by: Mapped[int] = mapped_column(ForeignKey('portal_users.id'))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utc_now)


class Enrollment(Base):
    __tablename__ = 'training_enrollments'
    __table_args__ = (UniqueConstraint('session_id', 'user_id', name='uq_training_participant'),
        CheckConstraint("status IN ('ENROLLED','REMOVED')"),
        CheckConstraint("attendance IN ('UNKNOWN','ATTENDED','ABSENT','EXCUSED')"),
        CheckConstraint("completion IN ('PENDING','COMPLETED','NOT_COMPLETED')"),
        CheckConstraint('version > 0'))
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey('training_sessions.id'), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('portal_users.id'), index=True)
    source_request_id: Mapped[int | None] = mapped_column(ForeignKey('requests.id'), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(20), default='ENROLLED')
    attendance: Mapped[str] = mapped_column(String(20), default='UNKNOWN')
    completion: Mapped[str] = mapped_column(String(20), default='PENDING')
    enrolled_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utc_now)
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utc_now)
    version: Mapped[int] = mapped_column(Integer, default=1)


class TrainingEvent(Base):
    __tablename__ = 'training_events'
    __table_args__ = (UniqueConstraint('session_id', 'version', name='uq_training_event_version'),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey('training_sessions.id'), index=True)
    version: Mapped[int] = mapped_column(Integer)
    action: Mapped[str] = mapped_column(String(32))
    from_status: Mapped[str] = mapped_column(String(20))
    to_status: Mapped[str] = mapped_column(String(20))
    actor_id: Mapped[int] = mapped_column(ForeignKey('portal_users.id'))
    actor_name: Mapped[str] = mapped_column(String(160))
    details_json: Mapped[str] = mapped_column(Text, default='{}')
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utc_now)


class TrainingNotification(Base):
    """Companion inbox source: training need not have a RequestEvent foreign key."""
    __tablename__ = 'training_notifications'
    __table_args__ = (UniqueConstraint('source_event_id', 'recipient_id', name='uq_training_notification_event_recipient'),
        Index('ix_training_notification_recipient_read', 'recipient_id', 'read_at', 'id'))
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    recipient_id: Mapped[int] = mapped_column(ForeignKey('portal_users.id'))
    session_id: Mapped[int] = mapped_column(ForeignKey('training_sessions.id'))
    source_event_id: Mapped[int] = mapped_column(ForeignKey('training_events.id'))
    title: Mapped[str] = mapped_column(String(180))
    message: Mapped[str] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utc_now)
    read_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)


GUARDS = [
    "CREATE TRIGGER IF NOT EXISTS training_version_immutable BEFORE UPDATE OF course_version_id ON training_sessions WHEN NEW.course_version_id IS NOT OLD.course_version_id BEGIN SELECT RAISE(ABORT, 'Session content version is immutable'); END",
    "CREATE TRIGGER IF NOT EXISTS training_published_source BEFORE INSERT ON training_sessions WHEN NOT EXISTS (SELECT 1 FROM course_versions v JOIN course_catalog c ON c.course_id=v.course_id WHERE v.id=NEW.course_version_id AND v.state='PUBLISHED' AND c.current_version_id=v.id) BEGIN SELECT RAISE(ABORT, 'Published current version required'); END",
    "CREATE TRIGGER IF NOT EXISTS training_capacity_insert BEFORE INSERT ON training_enrollments WHEN NEW.status='ENROLLED' AND (SELECT capacity FROM training_sessions WHERE id=NEW.session_id) <= (SELECT count(*) FROM training_enrollments WHERE session_id=NEW.session_id AND status='ENROLLED') BEGIN SELECT RAISE(ABORT, 'Training capacity exceeded'); END",
    "CREATE TRIGGER IF NOT EXISTS training_capacity_update BEFORE UPDATE OF status,session_id ON training_enrollments WHEN NEW.status='ENROLLED' AND (SELECT capacity FROM training_sessions WHERE id=NEW.session_id) <= (SELECT count(*) FROM training_enrollments WHERE session_id=NEW.session_id AND status='ENROLLED' AND id<>NEW.id) BEGIN SELECT RAISE(ABORT, 'Training capacity exceeded'); END",
    "CREATE TRIGGER IF NOT EXISTS training_capacity_lower BEFORE UPDATE OF capacity ON training_sessions WHEN NEW.capacity < (SELECT count(*) FROM training_enrollments WHERE session_id=NEW.id AND status='ENROLLED') BEGIN SELECT RAISE(ABORT, 'Capacity below enrollment count'); END",
    *[f"CREATE TRIGGER IF NOT EXISTS training_history_no_{op.lower()} BEFORE {op} ON training_events BEGIN SELECT RAISE(ABORT, 'Training history is append-only'); END" for op in ('UPDATE','DELETE')],
]
for statement in GUARDS:
    event.listen(TrainingNotification.__table__, 'after_create', DDL(statement).execute_if(dialect='sqlite'))


def install_guards(bind):
    if bind.dialect.name == 'sqlite':
        with bind.begin() as connection:
            for statement in GUARDS:
                connection.exec_driver_sql(statement)
