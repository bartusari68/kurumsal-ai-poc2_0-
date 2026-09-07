"""Aware UTC in Python; preserve the existing SQLite naive-UTC representation."""
from datetime import datetime, timezone
from sqlalchemy import DateTime
from sqlalchemy.types import TypeDecorator


def utc_now():
    return datetime.now(timezone.utc)


def as_utc(value):
    if value is None:
        return None
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def utc_stamp(value):
    return as_utc(value).isoformat().replace('+00:00', 'Z') if value else None


class UTCDateTime(TypeDecorator):
    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value, dialect):
        return as_utc(value).replace(tzinfo=None) if value else None

    def process_result_value(self, value, dialect):
        return as_utc(value)
