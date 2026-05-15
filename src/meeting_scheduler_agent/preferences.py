from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from meeting_scheduler_agent.models import CandidateSlot, TimeWindow, as_utc


@dataclass(frozen=True)
class BusinessHours:
    start: time
    end: time
    weekdays: tuple[int, ...] = (0, 1, 2, 3, 4)


@dataclass(frozen=True)
class SchedulingPreferences:
    organizer_email: str
    timezone_name: str
    business_hours: BusinessHours
    default_duration_minutes: int = 30
    meeting_buffer_minutes: int = 15
    slot_granularity_minutes: int = 30
    search_window_days: int = 10
    max_candidates: int = 3
    preferred_weekdays: tuple[int, ...] = (1, 2, 3)
    blackout_periods: tuple[TimeWindow, ...] = ()


def default_preferences(
    organizer_email: str,
    timezone_name: str = "America/Los_Angeles",
) -> SchedulingPreferences:
    return SchedulingPreferences(
        organizer_email=organizer_email,
        timezone_name=timezone_name,
        business_hours=BusinessHours(start=time(9, 0), end=time(17, 0)),
    )


def find_candidate_slots(
    busy_blocks: dict[str, list[TimeWindow]],
    window_start: datetime,
    window_end: datetime,
    duration_minutes: int,
    preferences: SchedulingPreferences,
) -> list[CandidateSlot]:
    tz = ZoneInfo(preferences.timezone_name)
    window_start = as_utc(window_start)
    window_end = as_utc(window_end)

    local_start_date = window_start.astimezone(tz).date()
    local_end_date = window_end.astimezone(tz).date()
    duration = timedelta(minutes=duration_minutes)
    granularity = timedelta(minutes=preferences.slot_granularity_minutes)

    slots: list[CandidateSlot] = []
    current_date = local_start_date
    while current_date <= local_end_date:
        if current_date.weekday() in preferences.business_hours.weekdays:
            slots.extend(
                _slots_for_day(
                    current_date,
                    tz,
                    window_start,
                    window_end,
                    duration,
                    granularity,
                    busy_blocks,
                    preferences,
                )
            )
        current_date += timedelta(days=1)

    return slots


def rank_candidate_slots(
    slots: list[CandidateSlot],
    preferences: SchedulingPreferences,
) -> list[CandidateSlot]:
    ranked: list[CandidateSlot] = []
    local_tz = ZoneInfo(preferences.timezone_name)

    for slot in slots:
        local_start = slot.start.astimezone(local_tz)
        score = 50.0

        if local_start.weekday() in preferences.preferred_weekdays:
            score += 20.0
        if 10 <= local_start.hour <= 15:
            score += 10.0
        if local_start.minute == 0:
            score += 3.0

        ranked.append(replace(slot, score=score, reason="Preference score"))

    return sorted(ranked, key=lambda slot: (-slot.score, slot.start))


def format_slot_for_email(slot: CandidateSlot, timezone_name: str) -> str:
    tz = ZoneInfo(timezone_name)
    local_start = slot.start.astimezone(tz)
    local_end = slot.end.astimezone(tz)
    return (
        f"{local_start.strftime('%A, %b %d at %I:%M %p')} - "
        f"{local_end.strftime('%I:%M %p %Z')}"
    )


def _slots_for_day(
    current_date: date,
    tz: ZoneInfo,
    window_start: datetime,
    window_end: datetime,
    duration: timedelta,
    granularity: timedelta,
    busy_blocks: dict[str, list[TimeWindow]],
    preferences: SchedulingPreferences,
) -> list[CandidateSlot]:
    local_open = datetime.combine(current_date, preferences.business_hours.start, tz)
    local_close = datetime.combine(current_date, preferences.business_hours.end, tz)

    day_start = max(local_open.astimezone(timezone.utc), window_start)
    day_end = min(local_close.astimezone(timezone.utc), window_end)
    cursor = _ceil_to_granularity(day_start, granularity)

    slots: list[CandidateSlot] = []
    while cursor + duration <= day_end:
        slot = CandidateSlot(start=cursor, end=cursor + duration)
        if _slot_is_available(slot, busy_blocks, preferences):
            slots.append(slot)
        cursor += granularity

    return slots


def _slot_is_available(
    slot: CandidateSlot,
    busy_blocks: dict[str, list[TimeWindow]],
    preferences: SchedulingPreferences,
) -> bool:
    buffer = timedelta(minutes=preferences.meeting_buffer_minutes)
    buffered_slot = TimeWindow(start=slot.start - buffer, end=slot.end + buffer)

    for blackout in preferences.blackout_periods:
        if _overlaps(buffered_slot, blackout):
            return False

    for attendee_blocks in busy_blocks.values():
        for busy_block in attendee_blocks:
            if _overlaps(buffered_slot, busy_block):
                return False

    return True


def _overlaps(left: TimeWindow, right: TimeWindow) -> bool:
    return as_utc(left.start) < as_utc(right.end) and as_utc(right.start) < as_utc(left.end)


def _ceil_to_granularity(value: datetime, granularity: timedelta) -> datetime:
    value = as_utc(value)
    seconds = int(granularity.total_seconds())
    timestamp = int(value.timestamp())
    remainder = timestamp % seconds
    if remainder == 0:
        return value
    return datetime.fromtimestamp(timestamp + (seconds - remainder), timezone.utc)
