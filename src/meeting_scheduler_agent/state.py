from __future__ import annotations

from typing import Literal, TypedDict

from meeting_scheduler_agent.models import CandidateSlot, EmailThread, MeetingRequest, TimeWindow

Intent = Literal["new_meeting", "reschedule", "cancel", "none"]


class SchedulingState(TypedDict, total=False):
    email_thread_id: str
    email_thread: EmailThread
    intent: Intent
    meeting_request: MeetingRequest
    busy_blocks: dict[str, list[TimeWindow]]
    candidate_slots: list[CandidateSlot]
    selected_slot: CandidateSlot | None
    draft_reply: str
    approval: dict[str, object]
    calendar_event_id: str
    send_result: dict[str, str]
    error: str
