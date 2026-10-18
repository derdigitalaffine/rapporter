from datetime import date

from rest_framework import permissions, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from .action_views import _family_membership
from .scheduling_rules import (
    describe_scheduling_rule,
    normalize_scheduling_rule,
    parse_scheduling_text,
    preview_occurrence_dates,
)


def _iso_date(value, label):
    if value in (None, ""):
        return None
    if not isinstance(value, str):
        raise ValueError(f"{label} muss ein ISO-Datum sein.")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{label} muss ein ISO-Datum sein.") from exc


@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def scheduling_preview(request):
    """Normalize/parse a recurrence rule and return a deterministic UI preview.

    The endpoint is intentionally read-only. It gives Event and Todo editors the
    exact server interpretation before either domain object is persisted.
    """

    family, _membership, error_response = _family_membership(request)
    if error_response is not None:
        return error_response

    data = request.data if isinstance(request.data, dict) else {}
    allowed = {"rule", "text", "anchor_date", "after", "limit", "language"}
    if not data or set(data) - allowed:
        return Response({"detail": "Ungültige Scheduling-Vorschau."}, status=status.HTTP_400_BAD_REQUEST)

    has_rule = isinstance(data.get("rule"), dict)
    has_text = isinstance(data.get("text"), str) and bool(data.get("text", "").strip())
    if has_rule == has_text:
        return Response(
            {"detail": "Genau eine Regel oder Texteingabe ist erforderlich."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    language = data.get("language") or family.locale or "de"
    if not isinstance(language, str) or not language.casefold().startswith(("de", "en")):
        return Response({"detail": "Nicht unterstützte Sprache."}, status=status.HTTP_400_BAD_REQUEST)

    limit = data.get("limit", 5)
    if type(limit) is not int or not 1 <= limit <= 10:
        return Response({"detail": "limit muss zwischen 1 und 10 liegen."}, status=status.HTTP_400_BAD_REQUEST)

    try:
        anchor_day = _iso_date(data.get("anchor_date"), "anchor_date")
        after_day = _iso_date(data.get("after"), "after")
        if has_text:
            rule = parse_scheduling_text(
                data["text"],
                family.timezone or "UTC",
                today=anchor_day,
            )
        else:
            raw_rule = dict(data["rule"])
            if anchor_day is not None and not raw_rule.get("anchor_date"):
                raw_rule["anchor_date"] = anchor_day.isoformat()
            rule = normalize_scheduling_rule(raw_rule, family.timezone or "UTC", anchor_date=anchor_day)
        summary = describe_scheduling_rule(rule, family.timezone or "UTC", language)
        occurrences = preview_occurrence_dates(
            rule,
            family.timezone or "UTC",
            after=after_day,
            limit=limit,
        )
    except (TypeError, ValueError) as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    return Response(
        {
            "rule": rule,
            "summary": summary,
            "occurrences": occurrences,
            "timezone": family.timezone or "UTC",
        }
    )
