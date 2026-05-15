from __future__ import annotations

import re
from datetime import timedelta
from typing import Literal

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from meeting_scheduler_agent.models import MeetingRequest, utc_now
from meeting_scheduler_agent.preferences import (
    SchedulingPreferences,
    find_candidate_slots,
    format_slot_for_email,
    rank_candidate_slots,
)
from meeting_scheduler_agent.state import SchedulingState
from meeting_scheduler_agent.tools import SchedulingTools


def build_graph(
    tools: SchedulingTools,
    preferences: SchedulingPreferences,
    *,
    auto_approve: bool = False,
):
    """Build the LangGraph workflow for the scheduling agent."""

    def load_email_thread(state: SchedulingState) -> SchedulingState:
        thread_id = state["email_thread_id"]
        return {"email_thread": tools.email.read_thread(thread_id)}

    def classify_intent(state: SchedulingState) -> SchedulingState:
        if state.get("waiting_for_reply") and not state.get("reply_received"):
            return {"workflow_status": "waiting_for_reply"}

        thread = state["email_thread"]
        text = " ".join([thread.subject, *[message.body for message in thread.messages]]).lower()

        if any(word in text for word in ["cancel", "called off"]):
            intent = "cancel"
        elif any(word in text for word in ["reschedule", "move our meeting", "move the meeting"]):
            intent = "reschedule"
        elif any(word in text for word in ["meet", "meeting", "call", "demo", "sync"]):
            intent = "new_meeting"
        else:
            intent = "none"

        return {"intent": intent}

    def route_after_intent(
        state: SchedulingState,
    ) -> Literal[
        "ignore_or_normal_reply",
        "extract_request",
        "load_existing_event",
        "cancel_or_update_event",
    ]:
        if state.get("waiting_for_reply") and not state.get("reply_received"):
            return "ignore_or_normal_reply"
        if state.get("intent") == "new_meeting":
            return "extract_request"
        if state.get("intent") == "reschedule":
            return "load_existing_event"
        if state.get("intent") == "cancel":
            return "cancel_or_update_event"
        return "ignore_or_normal_reply"

    def extract_request(state: SchedulingState) -> SchedulingState:
        return {"meeting_request": _request_from_thread(state, preferences)}

    def load_existing_event(state: SchedulingState) -> SchedulingState:
        thread = state["email_thread"]
        existing_event = tools.calendar.find_event_for_thread(thread.thread_id)
        if existing_event is None:
            return {
                "existing_event": None,
                "meeting_request": _request_from_thread(state, preferences),
                "error": "No existing calendar event found for this thread.",
            }

        duration_minutes = int((existing_event.end - existing_event.start).total_seconds() / 60)
        now = utc_now()
        request = MeetingRequest(
            title=existing_event.title,
            duration_minutes=duration_minutes,
            attendees=existing_event.attendees,
            window_start=now + timedelta(days=1),
            window_end=now + timedelta(days=preferences.search_window_days),
            source_thread_id=thread.thread_id,
        )
        return {"existing_event": existing_event, "meeting_request": request}

    def resolve_people_timezones_preferences(state: SchedulingState) -> SchedulingState:
        request = state["meeting_request"]
        participants = tools.contacts.lookup_people(request.attendees)
        timezones = {
            email: str(details.get("timezone") or preferences.timezone_name)
            for email, details in participants.items()
        }
        preference_summary = {
            "organizer_email": preferences.organizer_email,
            "organizer_timezone": preferences.timezone_name,
            "business_hours_start": preferences.business_hours.start.isoformat(timespec="minutes"),
            "business_hours_end": preferences.business_hours.end.isoformat(timespec="minutes"),
            "buffer_minutes": preferences.meeting_buffer_minutes,
            "preferred_weekdays": preferences.preferred_weekdays,
        }
        return {
            "participants": participants,
            "timezones": timezones,
            "preference_summary": preference_summary,
        }

    def check_availability(state: SchedulingState) -> SchedulingState:
        request = state["meeting_request"]
        busy_blocks = tools.calendar.get_busy_blocks(
            request.attendees,
            request.window_start,
            request.window_end,
        )
        return {"busy_blocks": busy_blocks}

    def rank_slots(state: SchedulingState) -> SchedulingState:
        request = state["meeting_request"]
        slots = find_candidate_slots(
            busy_blocks=state["busy_blocks"],
            window_start=request.window_start,
            window_end=request.window_end,
            duration_minutes=request.duration_minutes,
            preferences=preferences,
        )
        ranked_slots = rank_candidate_slots(slots, preferences)[: preferences.max_candidates]
        return {
            "candidate_slots": ranked_slots,
            "selected_slot": ranked_slots[0] if ranked_slots else None,
        }

    def draft_response_or_invite(state: SchedulingState) -> SchedulingState:
        if state.get("approval", {}).get("action") == "edit" and state.get("draft_reply"):
            return {"draft_reply": state["draft_reply"]}

        request = state["meeting_request"]
        slots = state.get("candidate_slots", [])
        verb = "reschedule" if state.get("intent") == "reschedule" else "schedule"

        if not slots:
            return {
                "draft_reply": (
                    "Thanks for reaching out. I could not find a good time in the current "
                    "availability window. Could you send a few windows that work on your side?"
                )
            }

        options = "\n".join(
            f"- {format_slot_for_email(slot, preferences.timezone_name)}" for slot in slots
        )
        reply = (
            f"Thanks - I can help {verb} {request.title}. Here are a few options that work:\n\n"
            f"{options}\n\n"
            "If one of these works, I can send over a calendar invite."
        )
        if state.get("error"):
            reply = f"{state['error']} I can still propose new times.\n\n{reply}"
        return {"draft_reply": reply}

    def approval_gate(
        state: SchedulingState,
    ) -> Command[
        Literal["send_email_or_create_invite", "draft_response_or_invite", "ignore_or_normal_reply"]
    ]:
        if auto_approve:
            return Command(
                goto="send_email_or_create_invite",
                update={"approval": {"action": "approve", "create_invite": False}},
            )

        review = interrupt(
            {
                "question": "Approve this scheduling response?",
                "draft_reply": state.get("draft_reply"),
                "selected_slot": state.get("selected_slot"),
            }
        )

        action = review.get("action")
        if action == "approve":
            return Command(goto="send_email_or_create_invite", update={"approval": review})
        if action == "edit":
            return Command(
                goto="draft_response_or_invite",
                update={
                    "approval": review,
                    "draft_reply": review.get("draft_reply", state.get("draft_reply")),
                },
            )
        return Command(goto="ignore_or_normal_reply", update={"approval": review})

    def send_email_or_create_invite(state: SchedulingState) -> SchedulingState:
        thread = state["email_thread"]
        draft = state["draft_reply"]
        approval = state.get("approval", {})
        selected_slot = state.get("selected_slot")
        calendar_event_id = state.get("calendar_event_id", "")

        if approval.get("create_invite") and selected_slot:
            if state.get("existing_event"):
                calendar_event_id = tools.calendar.update_event(
                    state["existing_event"].event_id,
                    selected_slot.start,
                    selected_slot.end,
                    draft,
                )
            else:
                request = state["meeting_request"]
                calendar_event_id = tools.calendar.create_event(
                    request.title,
                    request.attendees,
                    selected_slot.start,
                    selected_slot.end,
                    draft,
                    thread.thread_id,
                )

        send_result = tools.email.send_email(thread.thread_id, draft)
        return {"calendar_event_id": calendar_event_id, "send_result": send_result}

    def wait_for_replies(state: SchedulingState) -> SchedulingState:
        if auto_approve:
            return {
                "waiting_for_reply": True,
                "reply_received": False,
                "workflow_status": "waiting_for_reply",
            }

        reply = interrupt(
            {
                "status": "waiting_for_reply",
                "thread_id": state["email_thread"].thread_id,
                "message": "Resume this graph when a new email reply arrives.",
            }
        )
        thread_id = str(reply.get("email_thread_id", state["email_thread"].thread_id))
        return {
            "email_thread_id": thread_id,
            "email_thread": tools.email.read_thread(thread_id),
            "waiting_for_reply": False,
            "reply_received": True,
            "workflow_status": "reply_received",
        }

    def ignore_or_normal_reply(state: SchedulingState) -> SchedulingState:
        return {"workflow_status": state.get("workflow_status", "no_scheduling_action")}

    def cancel_or_update_event(state: SchedulingState) -> SchedulingState:
        thread = state["email_thread"]
        existing_event = tools.calendar.find_event_for_thread(thread.thread_id)
        if existing_event is None:
            draft = (
                "I can help with the cancellation, but I could not find a matching calendar "
                "event for this email thread."
            )
            cancellation_result = {"status": "not_found"}
        else:
            cancellation_result = tools.calendar.cancel_event(existing_event.event_id)
            draft = "Done - I cancelled the calendar event for this thread."

        send_result = tools.email.send_email(thread.thread_id, draft)
        return {
            "existing_event": existing_event,
            "draft_reply": draft,
            "cancellation_result": cancellation_result,
            "send_result": send_result,
            "workflow_status": "cancelled",
        }

    builder = StateGraph(SchedulingState)
    builder.add_node("load_email_thread", load_email_thread)
    builder.add_node("classify_intent", classify_intent)
    builder.add_node("ignore_or_normal_reply", ignore_or_normal_reply)
    builder.add_node("extract_request", extract_request)
    builder.add_node("load_existing_event", load_existing_event)
    builder.add_node("resolve_people_timezones_preferences", resolve_people_timezones_preferences)
    builder.add_node("check_availability", check_availability)
    builder.add_node("rank_slots", rank_slots)
    builder.add_node("draft_response_or_invite", draft_response_or_invite)
    builder.add_node("approval_gate", approval_gate)
    builder.add_node("send_email_or_create_invite", send_email_or_create_invite)
    builder.add_node("wait_for_replies", wait_for_replies)
    builder.add_node("cancel_or_update_event", cancel_or_update_event)

    builder.add_edge(START, "load_email_thread")
    builder.add_edge("load_email_thread", "classify_intent")
    builder.add_conditional_edges("classify_intent", route_after_intent)
    builder.add_edge("ignore_or_normal_reply", END)
    builder.add_edge("extract_request", "resolve_people_timezones_preferences")
    builder.add_edge("load_existing_event", "resolve_people_timezones_preferences")
    builder.add_edge("cancel_or_update_event", END)
    builder.add_edge("resolve_people_timezones_preferences", "check_availability")
    builder.add_edge("check_availability", "rank_slots")
    builder.add_edge("rank_slots", "draft_response_or_invite")
    builder.add_edge("draft_response_or_invite", "approval_gate")
    builder.add_edge("send_email_or_create_invite", "wait_for_replies")
    builder.add_edge("wait_for_replies", "classify_intent")

    return builder.compile(checkpointer=MemorySaver())


def _extract_duration_minutes(text: str) -> int | None:
    match = re.search(r"(\d+)\s*(minute|minutes|min|hour|hours|hr|hrs)", text, re.I)
    if not match:
        return None
    value = int(match.group(1))
    unit = match.group(2).lower()
    return value * 60 if unit.startswith(("hour", "hr")) else value


def _title_from_subject(subject: str) -> str:
    cleaned = re.sub(r"^(re|fw|fwd):\s*", "", subject, flags=re.I).strip()
    return cleaned or "Meeting"


def _request_from_thread(
    state: SchedulingState,
    preferences: SchedulingPreferences,
) -> MeetingRequest:
    thread = state["email_thread"]
    text = " ".join([thread.subject, *[message.body for message in thread.messages]])
    duration_minutes = _extract_duration_minutes(text) or preferences.default_duration_minutes
    participants = sorted(
        {
            email
            for message in thread.messages
            for email in [message.sender, *message.to]
            if email.lower() != preferences.organizer_email.lower()
        }
    )
    now = utc_now()
    return MeetingRequest(
        title=_title_from_subject(thread.subject),
        duration_minutes=duration_minutes,
        attendees=tuple(participants),
        window_start=now + timedelta(days=1),
        window_end=now + timedelta(days=preferences.search_window_days),
        source_thread_id=thread.thread_id,
    )
