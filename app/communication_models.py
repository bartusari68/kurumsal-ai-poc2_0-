"""Provider-independent communication delivery records.

In-app notifications remain in ``notifications`` and continue to be created by
the existing operation outbox.  This table is only the durable boundary for
optional external channels such as e-mail and Teams.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base
from .time_policy import UTCDateTime, utc_now


CHANNELS = ("IN_APP", "EMAIL", "TEAMS")
DELIVERY_STATUSES = ("PENDING", "PROCESSING", "SENT", "FAILED")


class CommunicationDelivery(Base):
    """One idempotent delivery per business event/channel/recipient."""

    __tablename__ = "communication_deliveries"
    __table_args__ = (
        CheckConstraint("channel IN ('IN_APP','EMAIL','TEAMS')"),
        CheckConstraint("status IN ('PENDING','PROCESSING','SENT','FAILED')"),
        UniqueConstraint(
            "business_event_key",
            "channel",
            "recipient_key",
            name="uq_communication_delivery_idempotency",
        ),
        Index("ix_communication_delivery_dispatch", "status", "next_attempt_at", "created_at"),
        Index("ix_communication_delivery_recipient", "recipient_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    business_event_key: Mapped[str] = mapped_column(String(160), index=True)
    channel: Mapped[str] = mapped_column(String(16), index=True)
    recipient_key: Mapped[str] = mapped_column(String(320))
    recipient_id: Mapped[int | None] = mapped_column(ForeignKey("portal_users.id"), nullable=True, index=True)
    recipient_address: Mapped[str] = mapped_column(String(320), default="")
    template_key: Mapped[str] = mapped_column(String(80), default="")
    title: Mapped[str] = mapped_column(String(180), default="")
    body: Mapped[str] = mapped_column(Text, default="")
    action_target: Mapped[str] = mapped_column(String(500), default="")
    related_event_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(16), default="PENDING", index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str] = mapped_column(Text, default="")
    sent_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    next_attempt_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utc_now)


# recipient_key is the canonical deduplication value.  It lets future service
# accounts or raw e-mail recipients use the same boundary without changing the
# existing PortalUser foreign-key graph.
