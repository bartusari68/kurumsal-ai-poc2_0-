"""Additive effectiveness records, independent of request and enrollment states."""
from datetime import datetime
from sqlalchemy import Integer, String, Text, ForeignKey, UniqueConstraint, CheckConstraint, Index, event, DDL
from sqlalchemy.orm import Mapped, mapped_column
from .database import Base
from .time_policy import UTCDateTime, utc_now


class LearningEvaluation(Base):
    __tablename__='learning_evaluations'
    __table_args__=(UniqueConstraint('enrollment_id','evaluation_type','evaluator_source',name='uq_evaluation_phase'),
        CheckConstraint("status IN ('PENDING','COMPLETED')"),
        CheckConstraint("evaluator_source IN ('PARTICIPANT','AUTHORIZED_REVIEWER')"),
        CheckConstraint("evaluation_type IN ('FEEDBACK','LEARNING','APPLICATION')"),
        CheckConstraint("outcome IS NULL OR outcome IN ('RESOLVED','PARTIALLY_RESOLVED','NOT_RESOLVED')"),
        CheckConstraint("(status='PENDING' AND submitted_at IS NULL AND response_json IS NULL AND outcome IS NULL) OR (status='COMPLETED' AND submitted_at IS NOT NULL AND response_json IS NOT NULL)"),
        CheckConstraint('version > 0'),
        Index('ix_eval_work','evaluator_id','status','available_at'))
    id: Mapped[int]=mapped_column(Integer,primary_key=True)
    enrollment_id: Mapped[int]=mapped_column(ForeignKey('training_enrollments.id'),index=True)
    course_version_id: Mapped[int]=mapped_column(ForeignKey('course_versions.id'),index=True)
    source_request_id: Mapped[int|None]=mapped_column(ForeignKey('requests.id'),nullable=True,index=True)
    evaluation_type: Mapped[str]=mapped_column(String(20))
    evaluator_source: Mapped[str]=mapped_column(String(24),default='PARTICIPANT')
    evaluator_id: Mapped[int]=mapped_column(ForeignKey('portal_users.id'))
    template_json: Mapped[str]=mapped_column(Text)
    completion_at: Mapped[datetime]=mapped_column(UTCDateTime)
    available_at: Mapped[datetime]=mapped_column(UTCDateTime,default=utc_now)
    due_at: Mapped[datetime|None]=mapped_column(UTCDateTime,nullable=True)
    status: Mapped[str]=mapped_column(String(20),default='PENDING')
    response_json: Mapped[str|None]=mapped_column(Text,nullable=True)
    outcome: Mapped[str|None]=mapped_column(String(24),nullable=True)
    submitted_at: Mapped[datetime|None]=mapped_column(UTCDateTime,nullable=True)
    version: Mapped[int]=mapped_column(Integer,default=1)
    created_by: Mapped[int]=mapped_column(ForeignKey('portal_users.id'))
    created_at: Mapped[datetime]=mapped_column(UTCDateTime,default=utc_now)


class EvaluationEvent(Base):
    __tablename__='evaluation_events'
    __table_args__=(UniqueConstraint('evaluation_id','version',name='uq_evaluation_event_version'),)
    id: Mapped[int]=mapped_column(Integer,primary_key=True)
    evaluation_id: Mapped[int]=mapped_column(ForeignKey('learning_evaluations.id'),index=True)
    version: Mapped[int]=mapped_column(Integer)
    action: Mapped[str]=mapped_column(String(24))
    actor_id: Mapped[int]=mapped_column(ForeignKey('portal_users.id'))
    actor_name: Mapped[str]=mapped_column(String(160))
    created_at: Mapped[datetime]=mapped_column(UTCDateTime,default=utc_now)


class EvaluationDelivery(Base):
    """Durable local outbox and notification receipt, unique per evaluation.

    No synthetic RequestEvent: evaluations without a request use their own event.
    Publication of the local notice is atomic and retryable, like training notices.
    """
    __tablename__='evaluation_deliveries'
    id: Mapped[int]=mapped_column(Integer,primary_key=True)
    evaluation_id: Mapped[int]=mapped_column(ForeignKey('learning_evaluations.id'),unique=True)
    source_event_id: Mapped[int]=mapped_column(ForeignKey('evaluation_events.id'))
    recipient_id: Mapped[int]=mapped_column(ForeignKey('portal_users.id'),index=True)
    deliver_at: Mapped[datetime]=mapped_column(UTCDateTime,index=True)
    processed_at: Mapped[datetime|None]=mapped_column(UTCDateTime,nullable=True,index=True)
    read_at: Mapped[datetime|None]=mapped_column(UTCDateTime,nullable=True)


GUARDS=[
 "CREATE TRIGGER IF NOT EXISTS evaluation_completed_source BEFORE INSERT ON learning_evaluations WHEN NOT EXISTS (SELECT 1 FROM training_enrollments e JOIN training_sessions s ON s.id=e.session_id WHERE e.id=NEW.enrollment_id AND e.status='ENROLLED' AND e.completion='COMPLETED' AND e.completed_at IS NOT NULL AND s.course_version_id=NEW.course_version_id AND e.source_request_id IS NEW.source_request_id AND (NEW.evaluator_source<>'PARTICIPANT' OR e.user_id=NEW.evaluator_id)) BEGIN SELECT RAISE(ABORT,'Completed enrollment context required'); END",
 "CREATE TRIGGER IF NOT EXISTS evaluation_context_immutable BEFORE UPDATE ON learning_evaluations WHEN NEW.enrollment_id IS NOT OLD.enrollment_id OR NEW.course_version_id IS NOT OLD.course_version_id OR NEW.source_request_id IS NOT OLD.source_request_id OR NEW.evaluation_type IS NOT OLD.evaluation_type OR NEW.evaluator_source IS NOT OLD.evaluator_source OR NEW.evaluator_id IS NOT OLD.evaluator_id OR NEW.template_json IS NOT OLD.template_json OR NEW.completion_at IS NOT OLD.completion_at OR NEW.created_by IS NOT OLD.created_by OR NEW.created_at IS NOT OLD.created_at OR NEW.available_at IS NOT OLD.available_at OR NEW.due_at IS NOT OLD.due_at BEGIN SELECT RAISE(ABORT,'Evaluation context is immutable'); END",
 "CREATE TRIGGER IF NOT EXISTS evaluation_submission_immutable BEFORE UPDATE ON learning_evaluations WHEN OLD.status='COMPLETED' OR NEW.status<>'COMPLETED' OR NEW.version<>OLD.version+1 BEGIN SELECT RAISE(ABORT,'Submitted evaluation is immutable'); END",
 "CREATE TRIGGER IF NOT EXISTS evaluation_no_delete BEFORE DELETE ON learning_evaluations BEGIN SELECT RAISE(ABORT,'Evaluation history is retained'); END",
 *[f"CREATE TRIGGER IF NOT EXISTS evaluation_event_no_{op.lower()} BEFORE {op} ON evaluation_events BEGIN SELECT RAISE(ABORT,'Evaluation audit is append-only'); END" for op in ('UPDATE','DELETE')],
]
for statement in GUARDS:
    event.listen(EvaluationDelivery.__table__,'after_create',DDL(statement).execute_if(dialect='sqlite'))


def install_guards(bind):
    if bind.dialect.name=='sqlite':
        with bind.begin() as connection:
            for statement in GUARDS: connection.exec_driver_sql(statement)
