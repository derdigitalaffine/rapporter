import re
from datetime import timedelta
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.db import transaction
from django.utils import timezone
from rest_framework import permissions, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from .action_views import _family_membership
from .create_action_models import CreateActionPreference, CreateActionStat, CreateActionUsageReceipt
from .create_action_ranking import ranking_payload
from .models import Family, Membership


ACTION_ID_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,47}$")
BUCKET_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,31}$")
MAX_STORED_IDS = 32
RECEIPT_RETENTION = timedelta(days=7)


def _safe_action_id(value, *, allow_blank=False):
    if allow_blank and value == "":
        return ""
    if not isinstance(value, str) or not ACTION_ID_RE.fullmatch(value):
        raise ValueError("Ungültige Create-Action-ID.")
    return value


def _safe_bucket(value):
    if value in (None, ""):
        return ""
    if not isinstance(value, str) or not BUCKET_RE.fullmatch(value):
        raise ValueError("Ungültiger Create-Kontext.")
    return value


def _id_list(value, name):
    if not isinstance(value, list) or len(value) > MAX_STORED_IDS:
        raise ValueError(f"{name} ist ungültig.")
    result = []
    for item in value:
        action_id = _safe_action_id(item)
        if action_id not in result:
            result.append(action_id)
    return result


def _preferences_patch(request, *, membership):
    data = request.data if isinstance(request.data, dict) else {}
    allowed = {
        "smart_ranking_enabled",
        "context_ranking_enabled",
        "time_patterns_enabled",
        "direct_mode",
        "direct_action_id",
        "max_quick_actions",
        "pinned_action_ids",
        "hidden_action_ids",
        "manual_order",
        "learning_scope",
        "reset_learning",
    }
    if not data or set(data) - allowed:
        return Response({"detail": "Ungültige Schnellstart-Präferenz."}, status=status.HTTP_400_BAD_REQUEST)
    for key in ("smart_ranking_enabled", "context_ranking_enabled", "time_patterns_enabled", "direct_mode", "reset_learning"):
        if key in data and type(data[key]) is not bool:
            return Response({"detail": f"{key} muss boolesch sein."}, status=status.HTTP_400_BAD_REQUEST)
    if "max_quick_actions" in data and (type(data["max_quick_actions"]) is not int or not 2 <= data["max_quick_actions"] <= 6):
        return Response({"detail": "max_quick_actions muss zwischen 2 und 6 liegen."}, status=status.HTTP_400_BAD_REQUEST)
    if "learning_scope" in data and data["learning_scope"] not in CreateActionPreference.LearningScope.values:
        return Response({"detail": "Unbekannter Lernbereich."}, status=status.HTTP_400_BAD_REQUEST)
    try:
        direct_action_id = _safe_action_id(data.get("direct_action_id", ""), allow_blank=True) if "direct_action_id" in data else None
        pinned = _id_list(data["pinned_action_ids"], "pinned_action_ids") if "pinned_action_ids" in data else None
        hidden = _id_list(data["hidden_action_ids"], "hidden_action_ids") if "hidden_action_ids" in data else None
        manual = _id_list(data["manual_order"], "manual_order") if "manual_order" in data else None
    except ValueError as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    with transaction.atomic():
        locked = Membership.objects.select_for_update().get(pk=membership.pk)
        setting, _ = CreateActionPreference.objects.get_or_create(membership=locked)
        final_pinned = pinned if pinned is not None else list(setting.pinned_action_ids or [])
        final_hidden = hidden if hidden is not None else list(setting.hidden_action_ids or [])
        if set(final_pinned) & set(final_hidden):
            return Response({"detail": "Eine Aktion kann nicht gleichzeitig angepinnt und ausgeblendet sein."}, status=status.HTTP_400_BAD_REQUEST)

        if data.get("reset_learning"):
            stats = CreateActionStat.objects.filter(membership=locked)
            receipts = CreateActionUsageReceipt.objects.filter(membership=locked)
            if setting.learning_scope == CreateActionPreference.LearningScope.GLOBAL:
                member_ids = Membership.objects.filter(
                    user=locked.user,
                    family__status=Family.Status.ACTIVE,
                ).values_list("id", flat=True)
                stats = CreateActionStat.objects.filter(membership_id__in=member_ids)
                receipts = CreateActionUsageReceipt.objects.filter(membership_id__in=member_ids)
            stats.delete()
            receipts.delete()

        fields = []
        for key in ("smart_ranking_enabled", "context_ranking_enabled", "time_patterns_enabled", "direct_mode", "max_quick_actions", "learning_scope"):
            if key in data:
                setattr(setting, key, data[key])
                fields.append(key)
        if direct_action_id is not None:
            setting.direct_action_id = direct_action_id
            fields.append("direct_action_id")
        if pinned is not None:
            setting.pinned_action_ids = pinned
            fields.append("pinned_action_ids")
        if hidden is not None:
            setting.hidden_action_ids = hidden
            fields.append("hidden_action_ids")
        if manual is not None:
            setting.manual_order = manual
            fields.append("manual_order")
        if fields:
            setting.save(update_fields=[*fields, "updated_at"])
        return Response(ranking_payload(locked))


def _increment_counter(data, key, *, max_keys=24):
    next_data = dict(data or {})
    if key:
        if key in next_data or len(next_data) < max_keys:
            next_data[key] = int(next_data.get(key, 0)) + 1
    return next_data


def _record_usage(request, *, family, membership):
    data = request.data if isinstance(request.data, dict) else {}
    allowed = {"event_id", "action_id", "origin_page", "context_bucket", "success"}
    if not data or set(data) - allowed or data.get("success") is not True:
        return Response({"detail": "Nur erfolgreiche Create-Aktionen können gelernt werden."}, status=status.HTTP_400_BAD_REQUEST)
    try:
        event_id = UUID(str(data.get("event_id", "")))
    except (ValueError, TypeError, AttributeError):
        return Response({"detail": "Ungültige event_id."}, status=status.HTTP_400_BAD_REQUEST)
    try:
        action_id = _safe_action_id(data.get("action_id"))
        origin_page = _safe_bucket(data.get("origin_page"))
        context_bucket = _safe_bucket(data.get("context_bucket"))
    except ValueError as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    now = timezone.now()
    try:
        local_now = now.astimezone(ZoneInfo(family.timezone or "UTC"))
    except ZoneInfoNotFoundError:
        local_now = now
    time_bucket = f"w{local_now.weekday()}-h{local_now.hour // 4}"
    context_key = context_bucket or origin_page

    with transaction.atomic():
        locked = Membership.objects.select_for_update().get(pk=membership.pk)
        CreateActionUsageReceipt.objects.filter(
            membership=locked,
            created_at__lt=now - RECEIPT_RETENTION,
        ).delete()
        receipt, created = CreateActionUsageReceipt.objects.get_or_create(
            event_id=event_id,
            defaults={
                "membership": locked,
                "action_id": action_id,
                "origin_page": origin_page,
                "context_bucket": context_bucket,
            },
        )
        if not created:
            if receipt.membership_id != locked.id or receipt.action_id != action_id:
                return Response({"detail": "Nutzungssignal wurde bereits verwendet."}, status=status.HTTP_409_CONFLICT)
            payload = ranking_payload(locked)
            payload.update({"accepted": True, "deduplicated": True})
            return Response(payload)
        stat, _ = CreateActionStat.objects.select_for_update().get_or_create(
            membership=locked,
            action_id=action_id,
        )
        stat.use_count += 1
        stat.last_used_at = now
        stat.context_stats = _increment_counter(stat.context_stats, context_key)
        stat.time_bucket_stats = _increment_counter(stat.time_bucket_stats, time_bucket)
        stat.save(update_fields=["use_count", "last_used_at", "context_stats", "time_bucket_stats", "updated_at"])
        payload = ranking_payload(locked)
        payload.update({"accepted": True, "deduplicated": False})
        return Response(payload, status=status.HTTP_201_CREATED)


@api_view(["GET", "PATCH", "POST"])
@permission_classes([permissions.IsAuthenticated])
def create_action_preferences(request):
    family, membership, error_response = _family_membership(request)
    if error_response is not None:
        return error_response
    if request.method == "PATCH":
        return _preferences_patch(request, membership=membership)
    if request.method == "POST":
        return _record_usage(request, family=family, membership=membership)
    return Response(ranking_payload(membership))
