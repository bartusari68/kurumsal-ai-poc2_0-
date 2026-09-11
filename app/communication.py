"""Optional communication delivery boundary built on the operation outbox."""

from __future__ import annotations

import smtplib
from datetime import timedelta
from email.message import EmailMessage
from typing import Any, Protocol

import httpx
from sqlalchemy import func, or_, select, update
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.orm import Session

from .communication_models import CommunicationDelivery, DELIVERY_STATUSES
from .config import settings
from .identity_models import ExternalIdentityLink, IntegrationAuditEvent, NotificationPreference
from .models import PortalUser
from .time_policy import utc_now, utc_stamp
from .utils import json_dumps


class DeliveryAdapter(Protocol):
    channel: str

    def enabled(self) -> bool: ...

    def deliver(self, delivery: CommunicationDelivery) -> None: ...


class DisabledAdapter:
    def __init__(self, channel: str):
        self.channel = channel

    def enabled(self) -> bool:
        return False

    def deliver(self, delivery: CommunicationDelivery) -> None:
        raise RuntimeError(f"{self.channel} sağlayıcısı yapılandırılmadı")


class InAppAdapter:
    """Marker adapter: in-app delivery is handled by the existing Notification table."""

    channel = "IN_APP"

    def enabled(self) -> bool:
        return True

    def deliver(self, delivery: CommunicationDelivery) -> None:
        return None


class SMTPEmailAdapter:
    channel = "EMAIL"

    def enabled(self) -> bool:
        return settings.email_configured

    def deliver(self, delivery: CommunicationDelivery) -> None:
        if not self.enabled():
            raise RuntimeError("E-posta sağlayıcısı yapılandırılmadı")
        if not delivery.recipient_address:
            raise RuntimeError("Alıcının e-posta adresi bulunamadı")
        message = EmailMessage()
        message["From"] = settings.email_from
        message["To"] = delivery.recipient_address
        message["Subject"] = delivery.title
        message.set_content(delivery.body)
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=settings.directory_timeout_seconds) as client:
            client.ehlo()
            if settings.smtp_username:
                client.starttls()
                client.login(settings.smtp_username, settings.smtp_password)
            client.send_message(message)


class TeamsAdapter:
    channel = "TEAMS"

    def enabled(self) -> bool:
        return settings.teams_configured

    def deliver(self, delivery: CommunicationDelivery) -> None:
        if not self.enabled():
            raise RuntimeError("Teams sağlayıcısı yapılandırılmadı")
        # The webhook is read only from settings and is never returned to UI or
        # written to logs.  No call is made while the adapter is disabled.
        response = httpx.post(settings.teams_webhook_url, json={"title": delivery.title, "text": delivery.body},
                              timeout=settings.directory_timeout_seconds)
        response.raise_for_status()


# Public names used by provider wiring and tests.
EmailAdapter = SMTPEmailAdapter
CommunicationAdapter = DeliveryAdapter


def adapter(channel: str) -> DeliveryAdapter:
    channel = channel.upper()
    if channel == "IN_APP":
        return InAppAdapter()
    if channel == "EMAIL":
        return SMTPEmailAdapter() if settings.email_configured else DisabledAdapter(channel)
    if channel == "TEAMS":
        return TeamsAdapter() if settings.teams_configured else DisabledAdapter(channel)
    return DisabledAdapter(channel)


def resolve_template(event_type: str, context: dict[str, Any] | None = None) -> dict[str, str]:
    """Resolve an operation event without embedding channel text in routes."""

    from .operations import EVENTS

    title, body, target = EVENTS.get(event_type, ("Kurumsal öğrenme güncellemesi", "Yeni bir işlem güncellemesi var.", "owner"))
    context = context or {}
    for key, value in context.items():
        title = title.replace("{" + str(key) + "}", str(value))
        body = body.replace("{" + str(key) + "}", str(value))
    return {"template_key": event_type, "title": title, "body": body, "action_target": target}


def _recipient_address(db: Session, recipient_id: int) -> str:
    row = db.scalar(select(ExternalIdentityLink).where(ExternalIdentityLink.user_id == recipient_id,
                                                       ExternalIdentityLink.status == "ACTIVE",
                                                       ExternalIdentityLink.email_snapshot != "").order_by(ExternalIdentityLink.id))
    return row.email_snapshot if row else ""


def _preference_enabled(db: Session, recipient_id: int, channel: str) -> bool:
    row = db.get(NotificationPreference, recipient_id)
    if row is None:
        # No row is fabricated.  Once an adapter is explicitly configured,
        # delivery is allowed until the user opts out.
        return True
    return bool(getattr(row, channel.lower(), False))


def enqueue_external_deliveries(db: Session, *, event_id: int, event_type: str, recipient_ids: list[int] | set[int],
                                context: dict[str, Any] | None = None) -> int:
    """Queue optional e-mail/Teams deliveries idempotently; never raises into workflow."""

    template = resolve_template(event_type, context)
    inserted = 0
    for recipient_id in sorted({int(identifier) for identifier in recipient_ids if identifier}):
        for channel in ("EMAIL", "TEAMS"):
            if not adapter(channel).enabled() or not _preference_enabled(db, recipient_id, channel):
                continue
            recipient = db.get(PortalUser, recipient_id)
            if not recipient or not recipient.active:
                continue
            address = _recipient_address(db, recipient_id) if channel == "EMAIL" else ""
            key = f"user:{recipient_id}"
            result = db.execute(insert(CommunicationDelivery).values(
                business_event_key=f"request-event:{event_id}", channel=channel, recipient_key=key,
                recipient_id=recipient_id, recipient_address=address, template_key=template["template_key"],
                title=template["title"], body=template["body"], action_target=template["action_target"],
                related_event_id=event_id, status="PENDING", attempts=0, last_error="", created_at=utc_now(),
                updated_at=utc_now()).on_conflict_do_nothing(index_elements=[
                    "business_event_key", "channel", "recipient_key"]))
            inserted += int(result.rowcount or 0)
    return inserted


def _retry_time(attempts: int):
    # A short, bounded backoff is enough for a POC; this is not an enterprise
    # SLA promise and never creates an unbounded hot retry loop.
    return utc_now() + timedelta(seconds=min(300, 30 * (2 ** max(0, attempts - 1))))


def dispatch_deliveries(factory, limit: int = 50) -> None:
    """Deliver queued external messages independently of business workflow."""

    with factory() as db:
        rows = list(db.scalars(select(CommunicationDelivery).where(
            CommunicationDelivery.status.in_(("PENDING", "FAILED")),
            CommunicationDelivery.attempts < 3,
            or_(CommunicationDelivery.next_attempt_at.is_(None), CommunicationDelivery.next_attempt_at <= utc_now())
        ).order_by(CommunicationDelivery.id).limit(limit)))
    for row in rows:
        with factory() as db:
            claimed = db.execute(update(CommunicationDelivery).where(
                CommunicationDelivery.id == row.id,
                CommunicationDelivery.status.in_(("PENDING", "FAILED")),
                CommunicationDelivery.attempts < 3,
            ).values(status="PROCESSING", attempts=CommunicationDelivery.attempts + 1, updated_at=utc_now()))
            if not claimed.rowcount:
                continue
            db.commit()
        try:
            with factory() as db:
                current = db.get(CommunicationDelivery, row.id)
                adapter(current.channel).deliver(current)
                current.status = "SENT"
                current.sent_at = utc_now()
                current.next_attempt_at = None
                current.last_error = ""
                current.updated_at = utc_now()
                db.add(IntegrationAuditEvent(action="communication_sent", provider=current.channel,
                                              user_id=current.recipient_id,
                                              details_json=json_dumps({"delivery_id": current.id,
                                                                       "business_event_key": current.business_event_key})))
                db.commit()
        except Exception as error:
            with factory() as db:
                current = db.get(CommunicationDelivery, row.id)
                if not current:
                    continue
                current.status = "FAILED"
                current.last_error = type(error).__name__
                current.next_attempt_at = _retry_time(current.attempts) if current.attempts < 3 else None
                current.updated_at = utc_now()
                db.add(IntegrationAuditEvent(action="communication_failed", provider=current.channel,
                                              user_id=current.recipient_id,
                                              details_json=json_dumps({"delivery_id": current.id,
                                                                       "business_event_key": current.business_event_key,
                                                                       "attempts": current.attempts})))
                db.commit()


def delivery_payload(row: CommunicationDelivery) -> dict[str, Any]:
    return {"id": row.id, "business_event_key": row.business_event_key, "channel": row.channel,
            "recipient_id": row.recipient_id, "recipient_address": (row.recipient_address[:2] + "***" if row.recipient_address else ""),
            "template_key": row.template_key, "title": row.title, "status": row.status,
            "attempts": row.attempts, "last_error": row.last_error, "sent_at": utc_stamp(row.sent_at),
            "next_attempt_at": utc_stamp(row.next_attempt_at), "created_at": utc_stamp(row.created_at)}


def delivery_status(db: Session, limit: int = 50) -> dict[str, Any]:
    rows = list(db.scalars(select(CommunicationDelivery).order_by(CommunicationDelivery.id.desc()).limit(limit)))
    counts = {status: db.scalar(select(func.count()).select_from(CommunicationDelivery).where(CommunicationDelivery.status == status)) or 0
              for status in DELIVERY_STATUSES}
    return {"channels": {"IN_APP": {"enabled": True}, "EMAIL": {"enabled": bool(settings.email_configured)},
                         "TEAMS": {"enabled": bool(settings.teams_configured)}}, "counts": counts,
            "items": [delivery_payload(row) for row in rows]}


def preference_payload(row: NotificationPreference | None, user_id: int) -> dict[str, Any]:
    return {"user_id": user_id, "in_app": bool(row.in_app) if row else True,
            "email": bool(row.email) if row else False, "teams": bool(row.teams) if row else False,
            "configured": bool(row)}


def update_preferences(db: Session, user_id: int, values: dict[str, Any]) -> dict[str, Any]:
    row = db.get(NotificationPreference, user_id)
    if row is None:
        row = NotificationPreference(user_id=user_id)
        db.add(row)
    for field in ("in_app", "email", "teams"):
        if field in values and values[field] is not None:
            setattr(row, field, bool(values[field]))
    row.updated_at = utc_now()
    db.commit()
    return preference_payload(row, user_id)
