from __future__ import annotations

from datetime import datetime, time, timedelta, timezone

from meeting_scheduler_agent.models import TimeWindow
from meeting_scheduler_agent.preferences import (
    BusinessHours,
    SchedulingPreferences,
    find_candidate_slots,
    rank_candidate_slots,
)


def test_candidate_slots_avoid_busy_blocks() -> None:
    preferences = SchedulingPreferences(
        organizer_email="rep@example.com",
        timezone_name="UTC",
        business_hours=BusinessHours(start=time(9), end=time(12)),
        meeting_buffer_minutes=0,
        slot_granularity_minutes=30,
    )
    busy_blocks = {
        "buyer@example.com": [
            TimeWindow(
                start=datetime(2026, 5, 18, 10, 0, tzinfo=timezone.utc),
                end=datetime(2026, 5, 18, 11, 0, tzinfo=timezone.utc),
            )
        ]
    }

    slots = find_candidate_slots(
        busy_blocks=busy_blocks,
        window_start=datetime(2026, 5, 18, 9, 0, tzinfo=timezone.utc),
        window_end=datetime(2026, 5, 18, 12, 0, tzinfo=timezone.utc),
        duration_minutes=30,
        preferences=preferences,
    )

    blocked_starts = {slot.start.time() for slot in slots}
    assert time(10, 0) not in blocked_starts
    assert time(10, 30) not in blocked_starts
    assert time(9, 0) in blocked_starts
    assert time(11, 0) in blocked_starts


def test_ranking_prefers_preferred_weekdays() -> None:
    preferences = SchedulingPreferences(
        organizer_email="rep@example.com",
        timezone_name="UTC",
        business_hours=BusinessHours(start=time(9), end=time(17)),
        preferred_weekdays=(1,),
    )
    monday = TimeWindow(
        start=datetime(2026, 5, 18, 10, 0, tzinfo=timezone.utc),
        end=datetime(2026, 5, 18, 10, 30, tzinfo=timezone.utc),
    )
    tuesday = TimeWindow(
        start=datetime(2026, 5, 19, 10, 0, tzinfo=timezone.utc),
        end=datetime(2026, 5, 19, 10, 30, tzinfo=timezone.utc),
    )
    slots = [
        _slot_from_window(monday),
        _slot_from_window(tuesday),
    ]

    ranked = rank_candidate_slots(slots, preferences)

    assert ranked[0].start.weekday() == 1


def _slot_from_window(window: TimeWindow):
    from meeting_scheduler_agent.models import CandidateSlot

    return CandidateSlot(start=window.start, end=window.end + timedelta(minutes=0))
