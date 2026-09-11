"""Additive portfolio records. Decision evidence and handoff receipts are immutable."""
from datetime import datetime
from sqlalchemy import Integer, String, Text, ForeignKey, CheckConstraint, UniqueConstraint, Index, text, event, DDL
from sqlalchemy.orm import Mapped, mapped_column
from .database import Base
from .time_policy import UTCDateTime, utc_now

class PortfolioItem(Base):
    __tablename__ = 'portfolio_items'
    __table_args__ = (CheckConstraint("state IN ('OPEN','UNDER_REVIEW','DECIDED','CLOSED')"),
        CheckConstraint('version > 0'),
        CheckConstraint("(state IN ('OPEN','UNDER_REVIEW') AND decision IS NULL) OR (state IN ('DECIDED','CLOSED') AND decision IS NOT NULL)"),
        CheckConstraint("decision IS NULL OR decision IN ('NO_ACTION','MONITOR','CREATE_NEW_LEARNING_NEED','START_COURSE_ENRICHMENT','PLAN_ADDITIONAL_SESSIONS')"),
        Index('uq_portfolio_active_skill_scope', 'skill_id', 'scope', unique=True, sqlite_where=text("state <> 'CLOSED'")))
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    skill_id: Mapped[int] = mapped_column(ForeignKey('skills.id'), index=True)
    title: Mapped[str] = mapped_column(String(255))
    scope: Mapped[str] = mapped_column(String(40), default='ORGANIZATION')
    owner_unit: Mapped[str] = mapped_column(String(40), default='NEEDS_ANALYST')
    assignee_id: Mapped[int | None] = mapped_column(ForeignKey('portal_users.id'), nullable=True)
    state: Mapped[str] = mapped_column(String(20), default='OPEN')
    rationale: Mapped[str] = mapped_column(Text)
    decision: Mapped[str | None] = mapped_column(String(40), nullable=True)
    decision_note: Mapped[str] = mapped_column(Text, default='')
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_by: Mapped[int] = mapped_column(ForeignKey('portal_users.id'))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utc_now)

class PortfolioEvent(Base):
    __tablename__ = 'portfolio_events'
    __table_args__ = (UniqueConstraint('item_id', 'version'),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    item_id: Mapped[int] = mapped_column(ForeignKey('portfolio_items.id'), index=True)
    version: Mapped[int] = mapped_column(Integer)
    action: Mapped[str] = mapped_column(String(24))
    from_state: Mapped[str | None] = mapped_column(String(20), nullable=True)
    to_state: Mapped[str] = mapped_column(String(20))
    actor_id: Mapped[int] = mapped_column(ForeignKey('portal_users.id'))
    actor_name: Mapped[str] = mapped_column(String(160))
    note: Mapped[str] = mapped_column(Text, default='')
    decision: Mapped[str | None] = mapped_column(String(40), nullable=True)
    snapshot_json: Mapped[str] = mapped_column(Text, default='{}')
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utc_now)

class PortfolioHandoff(Base):
    __tablename__ = 'portfolio_handoffs'
    __table_args__ = (UniqueConstraint('item_id', 'recipient_id', 'kind', 'target_key'),
        CheckConstraint("kind IN ('REQUEST','DEVELOPMENT','SESSION')"))
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    item_id: Mapped[int] = mapped_column(ForeignKey('portfolio_items.id'), index=True)
    decision_event_id: Mapped[int] = mapped_column(ForeignKey('portfolio_events.id'))
    recipient_id: Mapped[int] = mapped_column(ForeignKey('portal_users.id'), index=True)
    kind: Mapped[str] = mapped_column(String(20))
    target_key: Mapped[int] = mapped_column(Integer, default=0)
    context_json: Mapped[str] = mapped_column(Text)
    created_by: Mapped[int] = mapped_column(ForeignKey('portal_users.id'))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utc_now)

class PortfolioLink(Base):
    __tablename__ = 'portfolio_links'
    __table_args__ = (CheckConstraint('(request_id IS NOT NULL) + (development_id IS NOT NULL) + (session_id IS NOT NULL) = 1'),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    handoff_id: Mapped[int] = mapped_column(ForeignKey('portfolio_handoffs.id'), unique=True)
    request_id: Mapped[int | None] = mapped_column(ForeignKey('requests.id'), nullable=True)
    development_id: Mapped[int | None] = mapped_column(ForeignKey('development_items.id'), nullable=True)
    session_id: Mapped[int | None] = mapped_column(ForeignKey('training_sessions.id'), nullable=True)
    created_by: Mapped[int] = mapped_column(ForeignKey('portal_users.id'))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utc_now)

GUARDS = [
    "CREATE TRIGGER IF NOT EXISTS portfolio_handoff_decision BEFORE INSERT ON portfolio_handoffs WHEN NOT EXISTS (SELECT 1 FROM portfolio_items i JOIN portfolio_events e ON e.item_id=i.id WHERE i.id=NEW.item_id AND i.state='DECIDED' AND e.id=NEW.decision_event_id AND e.action='DECIDE' AND e.decision=i.decision) BEGIN SELECT RAISE(ABORT,'Current human decision required'); END",
    "CREATE TRIGGER IF NOT EXISTS portfolio_link_source BEFORE INSERT ON portfolio_links WHEN NOT EXISTS (SELECT 1 FROM portfolio_handoffs h WHERE h.id=NEW.handoff_id AND h.recipient_id=NEW.created_by AND ((h.kind='REQUEST' AND NEW.request_id IS NOT NULL AND EXISTS(SELECT 1 FROM request_workflows w WHERE w.request_id=NEW.request_id AND w.owner_hash=('user:'||h.recipient_id))) OR (h.kind='SESSION' AND NEW.session_id IS NOT NULL AND EXISTS(SELECT 1 FROM training_sessions s WHERE s.id=NEW.session_id AND s.course_version_id=h.target_key)) OR (h.kind='DEVELOPMENT' AND NEW.development_id IS NOT NULL AND EXISTS(SELECT 1 FROM development_items d WHERE d.id=NEW.development_id AND d.source_request_id=h.target_key AND d.work_type='COURSE_ENRICHMENT')))) BEGIN SELECT RAISE(ABORT,'Portfolio receipt must match its handoff'); END",
    *[f"CREATE TRIGGER IF NOT EXISTS {t}_no_delete BEFORE DELETE ON {t} BEGIN SELECT RAISE(ABORT,'Portfolio history is retained'); END" for t in ('portfolio_items','portfolio_events','portfolio_handoffs','portfolio_links')],
    *[f"CREATE TRIGGER IF NOT EXISTS {t}_immutable BEFORE UPDATE ON {t} BEGIN SELECT RAISE(ABORT,'Portfolio evidence is immutable'); END" for t in ('portfolio_events','portfolio_handoffs','portfolio_links')],
    "CREATE TRIGGER IF NOT EXISTS portfolio_item_context BEFORE UPDATE ON portfolio_items WHEN NEW.skill_id<>OLD.skill_id OR NEW.scope<>OLD.scope OR NEW.title<>OLD.title OR NEW.rationale<>OLD.rationale OR NEW.created_by<>OLD.created_by OR NEW.created_at IS NOT OLD.created_at OR NEW.owner_unit<>OLD.owner_unit OR NEW.assignee_id IS NOT OLD.assignee_id OR (OLD.decision IS NOT NULL AND (NEW.decision IS NOT OLD.decision OR NEW.decision_note<>OLD.decision_note)) BEGIN SELECT RAISE(ABORT,'Portfolio context and decision are retained'); END",
    "CREATE TRIGGER IF NOT EXISTS portfolio_item_transition BEFORE UPDATE ON portfolio_items WHEN NEW.version<>OLD.version+1 OR NOT ((OLD.state='OPEN' AND NEW.state='UNDER_REVIEW') OR (OLD.state='UNDER_REVIEW' AND NEW.state='DECIDED') OR (OLD.state='DECIDED' AND NEW.state='CLOSED')) BEGIN SELECT RAISE(ABORT,'Invalid portfolio transition'); END",
]
for statement in GUARDS:
    event.listen(Base.metadata, 'after_create', DDL(statement).execute_if(dialect='sqlite'))

def install(bind):
    if bind.dialect.name == 'sqlite':
        with bind.begin() as connection:
            for statement in GUARDS: connection.exec_driver_sql(statement)
