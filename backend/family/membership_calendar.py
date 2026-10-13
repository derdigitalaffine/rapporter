import hashlib
import re

from django.db import connection

CALENDAR_COLOR_PALETTE = (
    "#2F855A",  # green
    "#2563EB",  # blue
    "#7C3AED",  # violet
    "#DB2777",  # pink
    "#C2410C",  # orange
    "#0F766E",  # teal
    "#B91C1C",  # red
    "#4F46E5",  # indigo
)

_COLOR_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")


def normalize_calendar_color(value):
    value = str(value or "").strip().upper()
    if value not in CALENDAR_COLOR_PALETTE:
        raise ValueError("Bitte eine der angebotenen Kalenderfarben wählen.")
    return value


def fallback_calendar_color(membership_id):
    digest = hashlib.sha256(str(membership_id).encode("utf-8")).digest()
    return CALENDAR_COLOR_PALETTE[digest[0] % len(CALENDAR_COLOR_PALETTE)]


def get_calendar_color(membership):
    """Read the hotfix presentation column without changing the Membership model contract."""
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT calendar_color FROM family_membership WHERE id = %s",
            [membership.pk],
        )
        row = cursor.fetchone()
    value = (row[0] if row else "") or ""
    if _COLOR_RE.match(value) and value.upper() in CALENDAR_COLOR_PALETTE:
        return value.upper()
    return fallback_calendar_color(membership.pk)


def set_calendar_color(membership, value):
    color = normalize_calendar_color(value)
    with connection.cursor() as cursor:
        cursor.execute(
            "UPDATE family_membership SET calendar_color = %s WHERE id = %s",
            [color, membership.pk],
        )
    return color
