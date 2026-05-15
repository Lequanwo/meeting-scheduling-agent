from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass(frozen=True)
class EmailMessage:
    sender: str
    to: tuple[str, ...]
    subject: str
    body: str
    sent_at: datetime


@dataclass(frozen=True)
class EmailThread:
    thread_id: str
    subject: str
    messages: tuple[EmailMessage, ...]


@dataclass(frozen=True)
class MeetingRequest:
    title: str
    duration_minutes: int
    attendees: tuple[str, ...]
    window_start: datetime
    window_end: datetime
    source_thread_id: str


@dataclass(frozen=True)
class CalendarEvent:
    event_id: str
    title: str
    attendees: tuple[str, ...]
    start: datetime
    end: datetime
    source_thread_id: str


@dataclass(frozen=True)
class TimeWindow:
    start: datetime
    end: datetime
    label: str = ""


@dataclass(frozen=True)
class CandidateSlot:
    start: datetime
    end: datetime
    score: float = 0.0
    reason: str = ""


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
