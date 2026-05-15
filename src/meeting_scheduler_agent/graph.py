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

    def route_after_intent(state: SchedulingState) -> Literal["extract_request", "handle_cancel", "__end__"]:
        if state.get("intent") in {"new_meeting", "reschedule"}:
            return "extract_request"
        if state.get("intent") == "cancel":
            return "handle_cancel"
        return END

    def extract_request(state: SchedulingState) -> SchedulingState:
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
        request = MeetingRequest(
            title=_title_from_subject(thread.subject),
            duration_minutes=duration_minutes,
            attendees=tuple(participants),
            window_start=now + timedelta(days=1),
            window_end=now + timedelta(days=preferences.search_window_days),
            source_thread_id=thread.thread_id,
        )
        return {"meeting_request": request}

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

    def draft_reply(state: SchedulingState) -> SchedulingState:
        request = state["meeting_request"]
        slots = state.get("candidate_slots", [])

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
            f"Thanks - I can help schedule {request.title}. Here are a few options that work:\n\n"
            f"{options}\n\n"
            "If one of these works, I can send over a calendar invite."
        )
        return {"draft_reply": reply}

    def approval_gate(state: SchedulingState) -> Command[Literal["send_response", "__end__"]]:
        if auto_approve:
            return Command(goto="send_response", update={"approval": {"action": "approved"}})

        review = interrupt(
            {
                "question": "Approve this scheduling response?",
                "draft_reply": state.get("draft_reply"),
                "selected_slot": state.get("selected_slot"),
            }
        )

        action = review.get("action")
        if action == "approve":
            return Command(goto="send_response", update={"approval": review})
        if action == "edit":
            return Command(
                goto="send_response",
                update={
                    "approval": review,
                    "draft_reply": review.get("draft_reply", state.get("draft_reply")),
                },
            )
        return Command(goto=END, update={"approval": review})

    def send_response(state: SchedulingState) -> SchedulingState:
        thread = state["email_thread"]
        draft = state["draft_reply"]
        send_result = tools.email.send_email(thread.thread_id, draft)
        return {"send_result": send_result}

    def handle_cancel(state: SchedulingState) -> SchedulingState:
        thread = state["email_thread"]
        draft = (
            "I can help with the cancellation. I will confirm the calendar event before making "
            "changes so we do not cancel the wrong meeting."
        )
        send_result = tools.email.send_email(thread.thread_id, draft)
        return {"draft_reply": draft, "send_result": send_result}

    builder = StateGraph(SchedulingState)
    builder.add_node("load_email_thread", load_email_thread)
    builder.add_node("classify_intent", classify_intent)
    builder.add_node("extract_request", extract_request)
    builder.add_node("check_availability", check_availability)
    builder.add_node("rank_slots", rank_slots)
    builder.add_node("draft_reply", draft_reply)
    builder.add_node("approval_gate", approval_gate)
    builder.add_node("send_response", send_response)
    builder.add_node("handle_cancel", handle_cancel)

    builder.add_edge(START, "load_email_thread")
    builder.add_edge("load_email_thread", "classify_intent")
    builder.add_conditional_edges("classify_intent", route_after_intent)
    builder.add_edge("extract_request", "check_availability")
    builder.add_edge("check_availability", "rank_slots")
    builder.add_edge("rank_slots", "draft_reply")
    builder.add_edge("draft_reply", "approval_gate")
    builder.add_edge("send_response", END)
    builder.add_edge("handle_cancel", END)

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
