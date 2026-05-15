from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from meeting_scheduler_agent.models import CalendarEvent, EmailThread, TimeWindow


class EmailClient(Protocol):
    def read_thread(self, thread_id: str) -> EmailThread:
        ...

    def send_email(self, thread_id: str, body: str) -> dict[str, str]:
        ...


class CalendarClient(Protocol):
    def find_event_for_thread(self, thread_id: str) -> CalendarEvent | None:
        ...

    def get_busy_blocks(
        self,
        attendees: tuple[str, ...],
        window_start: datetime,
        window_end: datetime,
    ) -> dict[str, list[TimeWindow]]:
        ...

    def create_event(
        self,
        title: str,
        attendees: tuple[str, ...],
        start: datetime,
        end: datetime,
        description: str,
        source_thread_id: str,
    ) -> str:
        ...

    def update_event(
        self,
        event_id: str,
        start: datetime,
        end: datetime,
        description: str,
    ) -> str:
        ...

    def cancel_event(self, event_id: str) -> dict[str, str]:
        ...


class ContactClient(Protocol):
    def lookup_people(self, emails: tuple[str, ...]) -> dict[str, dict[str, object]]:
        ...


@dataclass(frozen=True)
class SchedulingTools:
    email: EmailClient
    calendar: CalendarClient
    contacts: ContactClient
