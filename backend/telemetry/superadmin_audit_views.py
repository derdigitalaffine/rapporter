import csv
import json
from datetime import timedelta
from io import StringIO
from uuid import UUID, uuid4

from django.http import HttpResponse
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from family.superadmin_views import IsSuperAdmin, _enforce_sensitive_action, _rate_limited_response

from .catalog import ACTOR_CLASSES, AUDIT_EVENT_SPECS, OUTCOMES, TARGET_TYPES
from .models import AuditEvent
from .service import try_record_audit_event


PERIODS = {"24h": 1, "7d": 7, "30d": 30, "90d": 90, "365d": 365}
DEFAULT_LIMIT = 50
MAX_LIMIT = 100
MAX_OFFSET = 10_000
MAX_EXPORT_ROWS = 5_000
# identifier_hash is deliberately excluded from the admin API even though it is
# valid telemetry metadata. The explorer should never expose entered login
# identifiers or stable derivatives of them.
SAFE_DETAIL_KEYS = frozenset({"auth_method", "role", "scope", "export_kind", "origin", "error_class", "source_key"})
CSV_COLUMNS = (
    "id",
    "occurred_at",
    "event_key",
    "actor_class",
    "actor_id",
    "family_id",
    "target_type",
    "target_id",
    "outcome",
    "reason",
    "request_id",
    "details",
)


def _positive_int(value, *, default, maximum, field):
    if value in (None, ""):
        return default, None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None, f"{field} must be an integer."
    if parsed < 0 or parsed > maximum:
        return None, f"{field} must be between 0 and {maximum}."
    return parsed, None


def _serialize_event(event):
    metadata = event.metadata if isinstance(event.metadata, dict) else {}
    details = {key: metadata[key] for key in SAFE_DETAIL_KEYS if key in metadata}
    return {
        "id": str(event.id),
        "occurred_at": event.occurred_at,
        "event_key": event.event_key,
        "actor_class": event.actor_class,
        "actor_id": event.actor_id,
        "family_id": event.family_id,
        "target_type": event.target_type,
        "target_id": event.target_id,
        "outcome": event.outcome,
        "reason": event.reason,
        "request_id": event.request_id,
        "details": details,
    }


def _csv_cell(value):
    if value is None:
        return ""
    if isinstance(value, dict):
        text = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    elif hasattr(value, "isoformat"):
        text = value.isoformat()
    else:
        text = str(value)
    if text.startswith(("=", "+", "-", "@")):
        return f"'{text}"
    return text


def _csv_response(events, *, period, export_id):
    stream = StringIO()
    writer = csv.DictWriter(stream, fieldnames=CSV_COLUMNS, extrasaction="ignore")
    writer.writeheader()
    for event in events:
        serialized = _serialize_event(event)
        writer.writerow({column: _csv_cell(serialized.get(column)) for column in CSV_COLUMNS})
    response = HttpResponse(stream.getvalue(), content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="familyos-audit-{period}-{timezone.now().date().isoformat()}.csv"'
    response["X-Audit-Export-Id"] = str(export_id)
    response["Cache-Control"] = "no-store"
    return response


@api_view(["GET"])
@permission_classes([IsSuperAdmin])
def superadmin_audit_events(request):
    period = str(request.query_params.get("period") or "30d").lower()
    days = PERIODS.get(period)
    if not days:
        return Response(
            {"detail": "Unsupported audit period.", "allowed_periods": list(PERIODS)},
            status=status.HTTP_400_BAD_REQUEST,
        )

    export_format = str(request.query_params.get("export") or "").lower()
    if export_format and export_format != "csv":
        return Response({"detail": "Unsupported audit export format."}, status=status.HTTP_400_BAD_REQUEST)
    if export_format and ("limit" in request.query_params or "offset" in request.query_params):
        return Response(
            {"detail": "Audit export does not accept pagination parameters."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    actor_class = str(request.query_params.get("actor_class") or "")
    if actor_class and actor_class not in ACTOR_CLASSES:
        return Response({"detail": "Unsupported actor_class."}, status=status.HTTP_400_BAD_REQUEST)

    outcome = str(request.query_params.get("outcome") or "")
    if outcome and outcome not in OUTCOMES:
        return Response({"detail": "Unsupported outcome."}, status=status.HTTP_400_BAD_REQUEST)

    event_key = str(request.query_params.get("event_key") or "")
    if event_key and event_key not in AUDIT_EVENT_SPECS:
        return Response({"detail": "Unsupported event_key."}, status=status.HTTP_400_BAD_REQUEST)

    target_type = str(request.query_params.get("target_type") or "")
    if target_type and target_type not in TARGET_TYPES:
        return Response({"detail": "Unsupported target_type."}, status=status.HTTP_400_BAD_REQUEST)

    limit, error = _positive_int(request.query_params.get("limit"), default=DEFAULT_LIMIT, maximum=MAX_LIMIT, field="limit")
    if error or limit == 0:
        return Response({"detail": error or "limit must be at least 1."}, status=status.HTTP_400_BAD_REQUEST)
    offset, error = _positive_int(request.query_params.get("offset"), default=0, maximum=MAX_OFFSET, field="offset")
    if error:
        return Response({"detail": error}, status=status.HTTP_400_BAD_REQUEST)

    family_id = request.query_params.get("family_id")
    if family_id not in (None, ""):
        try:
            family_id = str(UUID(str(family_id)))
        except (TypeError, ValueError, AttributeError):
            return Response({"detail": "family_id must be a UUID."}, status=status.HTTP_400_BAD_REQUEST)

    actor_id = request.query_params.get("actor_id")
    if actor_id not in (None, ""):
        try:
            actor_id = int(actor_id)
        except (TypeError, ValueError):
            return Response({"detail": "actor_id must be an integer."}, status=status.HTTP_400_BAD_REQUEST)
        if actor_id < 1:
            return Response({"detail": "actor_id must be positive."}, status=status.HTTP_400_BAD_REQUEST)

    end = timezone.now()
    start = end - timedelta(days=days)
    queryset = AuditEvent.objects.filter(occurred_at__gte=start, occurred_at__lt=end)
    if actor_class:
        queryset = queryset.filter(actor_class=actor_class)
    if outcome:
        queryset = queryset.filter(outcome=outcome)
    if event_key:
        queryset = queryset.filter(event_key=event_key)
    if target_type:
        queryset = queryset.filter(target_type=target_type)
    if family_id:
        queryset = queryset.filter(family_id=family_id)
    if actor_id:
        queryset = queryset.filter(actor_id=actor_id)

    queryset = queryset.order_by("-occurred_at", "id")
    total = queryset.count()

    if export_format == "csv":
        if total > MAX_EXPORT_ROWS:
            return Response(
                {"detail": "Audit export exceeds the maximum row count.", "max_rows": MAX_EXPORT_ROWS, "count": total},
                status=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            )
        decision = _enforce_sensitive_action(request)
        if not decision.allowed:
            return _rate_limited_response(decision)
        events = list(queryset)
        export_id = uuid4()
        try_record_audit_event(
            "superadmin.export.created",
            actor=request.user,
            actor_class="superadmin",
            outcome="success",
            reason="admin_action",
            target_type="export",
            target_id=str(export_id),
            metadata={"export_kind": "audit_csv"},
        )
        return _csv_response(events, period=period, export_id=export_id)

    events = list(queryset[offset : offset + limit])
    next_offset = offset + limit if offset + limit < total else None

    return Response(
        {
            "period": {"key": period, "start": start, "end": end, "timezone": "UTC"},
            "filters": {
                "actor_class": actor_class or None,
                "actor_id": actor_id or None,
                "event_key": event_key or None,
                "outcome": outcome or None,
                "family_id": family_id or None,
                "target_type": target_type or None,
            },
            "pagination": {"count": total, "limit": limit, "offset": offset, "next_offset": next_offset},
            "results": [_serialize_event(event) for event in events],
            "privacy": {
                "metadata_policy": "allow_list",
                "excluded": ["identifier_hash", "private_content", "tokens", "credential_material"],
            },
        }
    )
