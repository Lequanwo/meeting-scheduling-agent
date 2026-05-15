from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    organizer_email: str
    timezone: str


def load_settings() -> Settings:
    return Settings(
        organizer_email=os.getenv("SCHEDULER_ORGANIZER_EMAIL", "sales.rep@example.com"),
        timezone=os.getenv("SCHEDULER_TIMEZONE", "America/Los_Angeles"),
    )
