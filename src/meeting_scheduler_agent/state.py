from __future__ import annotations

from typing import Literal, TypedDict

from meeting_scheduler_agent.models import (
    CalendarEvent,
    CandidateSlot,
    EmailThread,
    MeetingRequest,
    TimeWindow,
)

Intent = Literal["new_meeting", "reschedule", "cancel", "none"]


class SchedulingState(TypedDict, total=False):
    email_thread_id: str
    email_thread: EmailThread
    intent: Intent
    existing_event: CalendarEvent | None
    meeting_request: MeetingRequest
    participants: dict[str, dict[str, object]]
    timezones: dict[str, str]
    preference_summary: dict[str, object]
    busy_blocks: dict[str, list[TimeWindow]]
    candidate_slots: list[CandidateSlot]
    selected_slot: CandidateSlot | None
    draft_reply: str
    approval: dict[str, object]
    calendar_event_id: str
    send_result: dict[str, str]
    cancellation_result: dict[str, str]
    waiting_for_reply: bool
    reply_received: bool
    workflow_status: str
    error: str
