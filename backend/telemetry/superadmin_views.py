from datetime import timedelta

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from auth_identity.models import EmailIdentity
from family.models import Family
from family.superadmin_views import IsSuperAdmin

from .models import AuditEvent, DailyRollup, UsageEvent
from .service import METRIC_ACTIVE_FAMILIES, METRIC_ACTIVE_USERS


PERIODS = {"24h": 1, "7d": 7, "30d": 30, "90d": 90, "365d": 365}


def _window(days, *, now=None):
    now = now or timezone.now()
    end = now
    start = end - timedelta(days=days)
    previous_start = start - timedelta(days=days)
    return start, end, previous_start


def _change(current, previous):
    delta = current - previous
    percentage = None if previous == 0 else round((delta / previous) * 100, 1)
    return {"value": current, "previous": previous, "delta": delta, "change_pct": percentage}


def _rate(numerator, denominator):
    return None if denominator == 0 else round((numerator / denominator) * 100, 1)


def _active_counts(start, end):
    activity = UsageEvent.objects.filter(
        event_key="activity.foreground",
        occurred_at__gte=start,
        occurred_at__lt=end,
    )
    return {
        "users": activity.values("user_id").distinct().count(),
        "families": activity.values("family_id").distinct().count(),
    }


def _daily_series(start, end):
    rows = DailyRollup.objects.filter(
        family__isnull=True,
        dimension_key="",
        day__gte=start.date(),
        day__lte=end.date(),
        metric_key__in=[METRIC_ACTIVE_USERS, METRIC_ACTIVE_FAMILIES],
    ).order_by("day", "metric_key")
    by_day = {}
    for row in rows:
        item = by_day.setdefault(row.day.isoformat(), {"day": row.day.isoformat(), "active_users": 0, "active_families": 0})
        if row.metric_key == METRIC_ACTIVE_USERS:
            item["active_users"] = row.value
        elif row.metric_key == METRIC_ACTIVE_FAMILIES:
            item["active_families"] = row.value
    return list(by_day.values())


def _audit_count(event_key, start, end, **filters):
    return AuditEvent.objects.filter(
        event_key=event_key,
        occurred_at__gte=start,
        occurred_at__lt=end,
        **filters,
    ).count()


def _security_counts(start, end):
    login_success = _audit_count("auth.login.succeeded", start, end)
    login_failure = _audit_count("auth.login.failed", start, end)
    password_logins = _audit_count("auth.login.succeeded", start, end, metadata__auth_method="password")
    passkey_logins = _audit_count("auth.login.succeeded", start, end, metadata__auth_method="passkey")
    legacy_logins = _audit_count("auth.login.succeeded", start, end, metadata__auth_method="legacy")
    return {
        "login_success": login_success,
        "login_failure": login_failure,
        "rate_limited": _audit_count("auth.rate_limited", start, end),
        "password_reset_completed": _audit_count("auth.password_reset.completed", start, end),
        "email_verified": _audit_count("auth.email.verified", start, end),
        "passkey_registered": _audit_count("auth.passkey.registered", start, end),
        "passkey_removed": _audit_count("auth.passkey.removed", start, end),
        "session_revoked": _audit_count("auth.session.revoked", start, end),
        "auth_methods": {
            "password": password_logins,
            "passkey": passkey_logins,
            "legacy": legacy_logins,
        },
    }


@api_view(["GET"])
@permission_classes([IsSuperAdmin])
def superadmin_analytics_overview(request):
    period = str(request.query_params.get("period") or "30d").lower()
    days = PERIODS.get(period)
    if not days:
        return Response(
            {"detail": "Unsupported analytics period.", "allowed_periods": list(PERIODS)},
            status=status.HTTP_400_BAD_REQUEST,
        )

    start, end, previous_start = _window(days)
    current_activity = _active_counts(start, end)
    previous_activity = _active_counts(previous_start, start)

    User = get_user_model()
    current_new_users = User.objects.filter(date_joined__gte=start, date_joined__lt=end).count()
    previous_new_users = User.objects.filter(date_joined__gte=previous_start, date_joined__lt=start).count()
    current_new_families = Family.objects.filter(created_at__gte=start, created_at__lt=end).count()
    previous_new_families = Family.objects.filter(created_at__gte=previous_start, created_at__lt=start).count()

    family_status = {
        "total": Family.objects.count(),
        "active": Family.objects.filter(status=Family.Status.ACTIVE).count(),
        "suspended": Family.objects.filter(status=Family.Status.SUSPENDED).count(),
    }
    verified_users = (
        EmailIdentity.objects.filter(kind=EmailIdentity.Kind.PRIMARY, verified_at__isnull=False)
        .values("user_id")
        .distinct()
        .count()
    )

    return Response(
        {
            "period": {
                "key": period,
                "days": days,
                "start": start,
                "end": end,
                "comparison_start": previous_start,
                "timezone": "UTC",
            },
            "totals": {
                "families": family_status,
                "users": User.objects.count(),
                "verified_email_users": verified_users,
            },
            "activity": {
                "active_users": _change(current_activity["users"], previous_activity["users"]),
                "active_families": _change(current_activity["families"], previous_activity["families"]),
                "new_users": _change(current_new_users, previous_new_users),
                "new_families": _change(current_new_families, previous_new_families),
            },
            "timeseries": _daily_series(start, end),
            "definitions": {
                "active_user": "Authenticated user with at least one activity.foreground usage event in the selected period.",
                "active_family": "Family with at least one activity.foreground usage event in the selected period.",
                "verified_email_user": "User with a verified primary EmailIdentity.",
                "comparison": "Immediately preceding period of equal length; change_pct is null when the previous value is zero.",
                "timeseries": "Daily distinct activity from telemetry DailyRollup; no private family content is queried.",
            },
        }
    )


@api_view(["GET"])
@permission_classes([IsSuperAdmin])
def superadmin_security_summary(request):
    period = str(request.query_params.get("period") or "30d").lower()
    days = PERIODS.get(period)
    if not days:
        return Response(
            {"detail": "Unsupported analytics period.", "allowed_periods": list(PERIODS)},
            status=status.HTTP_400_BAD_REQUEST,
        )

    start, end, previous_start = _window(days)
    current = _security_counts(start, end)
    previous = _security_counts(previous_start, start)
    login_total = current["login_success"] + current["login_failure"]
    successful_auth_methods = sum(current["auth_methods"].values())

    return Response(
        {
            "period": {
                "key": period,
                "days": days,
                "start": start,
                "end": end,
                "comparison_start": previous_start,
                "timezone": "UTC",
            },
            "authentication": {
                "login_success": _change(current["login_success"], previous["login_success"]),
                "login_failure": _change(current["login_failure"], previous["login_failure"]),
                "login_success_rate_pct": _rate(current["login_success"], login_total),
                "successful_login_methods": current["auth_methods"],
                "passkey_share_pct": _rate(current["auth_methods"]["passkey"], successful_auth_methods),
            },
            "security_events": {
                "rate_limited": _change(current["rate_limited"], previous["rate_limited"]),
                "password_reset_completed": _change(
                    current["password_reset_completed"], previous["password_reset_completed"]
                ),
                "email_verified": _change(current["email_verified"], previous["email_verified"]),
                "passkey_registered": _change(current["passkey_registered"], previous["passkey_registered"]),
                "passkey_removed": _change(current["passkey_removed"], previous["passkey_removed"]),
                "session_revoked": _change(current["session_revoked"], previous["session_revoked"]),
            },
            "definitions": {
                "login_success_rate_pct": "Successful login events divided by successful plus failed login events; null when there are no login events.",
                "passkey_share_pct": "Successful passkey login events divided by successful login events with a canonical auth_method; null when there are none.",
                "rate_limited": "Count of canonical auth.rate_limited audit events, without exposing attempted identifiers.",
                "privacy": "Only allow-listed aggregate audit event keys and auth_method categories are returned; identifiers, request IDs and event metadata are not exposed.",
            },
        }
    )
