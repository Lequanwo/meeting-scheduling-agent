from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from meeting_scheduler_agent.models import CalendarEvent, EmailMessage, EmailThread, TimeWindow
from meeting_scheduler_agent.tools import CalendarClient, ContactClient, EmailClient, SchedulingTools


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
        tz = ZoneInfo(timezone_name)
        start = datetime.combine(datetime.now(tz).date() + timedelta(days=4), time(14, 0), tz)
        self.events: dict[str, CalendarEvent] = {
            "thread-demo-1": CalendarEvent(
                event_id="mock-event-1",
                title="Intro call with Acme",
                attendees=("morgan@acme.example",),
                start=start.astimezone(timezone.utc),
                end=(start + timedelta(minutes=30)).astimezone(timezone.utc),
                source_thread_id="thread-demo-1",
            )
        }

    def find_event_for_thread(self, thread_id: str) -> CalendarEvent | None:
        return self.events.get(thread_id)

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
        source_thread_id: str,
    ) -> str:
        event_id = f"mock-event-{len(self.events) + 1}"
        self.events[source_thread_id] = CalendarEvent(
            event_id=event_id,
            title=title,
            attendees=attendees,
            start=start,
            end=end,
            source_thread_id=source_thread_id,
        )
        return event_id

    def update_event(
        self,
        event_id: str,
        start: datetime,
        end: datetime,
        description: str,
    ) -> str:
        event = next((item for item in self.events.values() if item.event_id == event_id), None)
        if event is None:
            raise ValueError(f"Calendar event not found: {event_id}")

        self.events[event.source_thread_id] = CalendarEvent(
            event_id=event.event_id,
            title=event.title,
            attendees=event.attendees,
            start=start,
            end=end,
            source_thread_id=event.source_thread_id,
        )
        return event_id

    def cancel_event(self, event_id: str) -> dict[str, str]:
        event = next((item for item in self.events.values() if item.event_id == event_id), None)
        if event is None:
            return {"event_id": event_id, "status": "not_found"}

        self.events.pop(event.source_thread_id, None)
        return {"event_id": event_id, "status": "cancelled"}


class MockContactClient:
    def lookup_people(self, emails: tuple[str, ...]) -> dict[str, dict[str, object]]:
        return {
            email: {
                "email": email,
                "name": email.split("@")[0].replace(".", " ").title(),
                "timezone": "America/Los_Angeles",
            }
            for email in emails
        }


def build_mock_tools(organizer_email: str) -> SchedulingTools:
    return SchedulingTools(
        email=MockEmailClient(organizer_email=organizer_email),
        calendar=MockCalendarClient(),
        contacts=MockContactClient(),
    )
