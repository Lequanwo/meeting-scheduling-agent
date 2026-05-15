from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from meeting_scheduler_agent.models import EmailMessage, EmailThread, TimeWindow
from meeting_scheduler_agent.tools import CalendarClient, EmailClient, SchedulingTools


class MockEmailClient:
    def __init__(self, organizer_email: str) -> None:
        self.organizer_email = organizer_email
        self.sent_messages: list[dict[str, str]] = []

    def read_thread(self, thread_id: str) -> EmailThread:
        now = datetime.now(timezone.utc)
        return EmailThread(
            thread_id=thread_id,
            subject="Intro call with Acme",
            messages=(
                EmailMessage(
                    sender="morgan@acme.example",
                    to=(self.organizer_email,),
                    subject="Intro call with Acme",
                    body=(
                        "Hi, could we schedule a 30 minute demo next week? "
                        "Afternoons tend to work better for our team."
                    ),
                    sent_at=now,
                ),
            ),
        )

    def send_email(self, thread_id: str, body: str) -> dict[str, str]:
        result = {"thread_id": thread_id, "body": body, "status": "sent"}
        self.sent_messages.append(result)
        return result


class MockCalendarClient:
    def __init__(self, timezone_name: str = "America/Los_Angeles") -> None:
        self.timezone_name = timezone_name
        self.events: list[dict[str, object]] = []

    def get_busy_blocks(
        self,
        attendees: tuple[str, ...],
        window_start: datetime,
        window_end: datetime,
    ) -> dict[str, list[TimeWindow]]:
        tz = ZoneInfo(self.timezone_name)
        today = datetime.now(tz).date()
        busy_start = datetime.combine(today + timedelta(days=2), time(13, 0), tz)
        busy_end = busy_start + timedelta(hours=1)

        return {
            attendee: [
                TimeWindow(
                    start=busy_start.astimezone(timezone.utc),
                    end=busy_end.astimezone(timezone.utc),
                    label="Existing meeting",
                )
            ]
            for attendee in attendees
        }

    def create_event(
        self,
        title: str,
        attendees: tuple[str, ...],
        start: datetime,
        end: datetime,
        description: str,
    ) -> str:
        event_id = f"mock-event-{len(self.events) + 1}"
        self.events.append(
            {
                "id": event_id,
                "title": title,
                "attendees": attendees,
                "start": start,
                "end": end,
                "description": description,
            }
        )
        return event_id


def build_mock_tools(organizer_email: str) -> SchedulingTools:
    return SchedulingTools(
        email=MockEmailClient(organizer_email=organizer_email),
        calendar=MockCalendarClient(),
    )
