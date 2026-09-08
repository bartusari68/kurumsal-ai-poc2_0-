"""Aware UTC in Python; preserve the existing SQLite naive-UTC representation."""
from datetime import datetime, timezone, timedelta, time
from sqlalchemy import DateTime
from sqlalchemy.types import TypeDecorator


def utc_now():
    return datetime.now(timezone.utc)


def training_day_bounds(day):
    """Training calendar uses the institution's explicit UTC+03:00 display zone.

    No operating-system timezone database is required on Windows. Storage stays UTC.
    """
    start = datetime.combine(day, time.min, tzinfo=timezone(timedelta(hours=3)))
    return start, start + timedelta(days=1)


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
