"""Compatibility adapter for recurrence text parsing.

The deterministic DE/EN grammar lives in ``action_schedule.parse_schedule``.
Keep this function for existing imports while routing every caller through the
same canonical parser path.
"""
from __future__ import annotations

from datetime import date

from .scheduling_rules import parse_scheduling_text


def parse_flexible_scheduling_text(text: str, family_timezone: str, today: date | None = None):
    return parse_scheduling_text(text, family_timezone, today=today)
