from datetime import timedelta
from statistics import median

from django.contrib.auth import get_user_model
from django.db.models import Min, Q
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from auth_identity.models import EmailIdentity
from family.models import Family
from family.superadmin_views import IsSuperAdmin

from .models import AuditEvent, DailyRollup, UsageEvent
from .service import METRIC_ACTIVE_FAMILIES, METRIC_ACTIVE_USERS
from .superadmin_activation import activation_overview, rolling_engagement


PERIODS = {"24h": 1, "7d": 7, "30d": 30, "90d": 90, "365d": 365}
INVITE_FUNNEL_EVENT_KEYS = (
    "invite.created",
    "invite.sent",
    "invite.email_failed",
    "invite.accepted",
    "invite.expired",
    "invite.revoked",
)


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


def _nullable_change(current, previous):
    delta = None if current is None or previous is None else current - previous
    percentage = None
    if current is not None and previous not in (None, 0):
        percentage = round(((current - previous) / previous) * 100, 1)
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


def _invite_funnel(start, end, *, role=None):
    events = AuditEvent.objects.filter(
        target_type="invite",
        event_key__in=INVITE_FUNNEL_EVENT_KEYS,
        occurred_at__gte=start,
        occurred_at__lt=end,
    )
    if role:
        events = events.filter(metadata__role=role)

    rows = list(
        events.values("target_id")
        .annotate(
            created_at=Min("occurred_at", filter=Q(event_key="invite.created")),
            sent_at=Min("occurred_at", filter=Q(event_key="invite.sent")),
            email_failed_at=Min("occurred_at", filter=Q(event_key="invite.email_failed")),
            accepted_at=Min("occurred_at", filter=Q(event_key="invite.accepted")),
            expired_at=Min("occurred_at", filter=Q(event_key="invite.expired")),
            revoked_at=Min("occurred_at", filter=Q(event_key="invite.revoked")),
        )
        .filter(created_at__isnull=False)
    )
    durations = [
        int((row["accepted_at"] - row["created_at"]).total_seconds())
        for row in rows
        if row["accepted_at"] is not None and row["accepted_at"] >= row["created_at"]
    ]
    result = {
        "created": len(rows),
        "sent": sum(1 for row in rows if row["sent_at"] is not None),
        "accepted": sum(1 for row in rows if row["accepted_at"] is not None),
        "email_failed": sum(1 for row in rows if row["email_failed_at"] is not None),
        "expired": sum(1 for row in rows if row["expired_at"] is not None),
        "revoked": sum(1 for row in rows if row["revoked_at"] is not None),
    }
    result["send_to_accept_rate_pct"] = _rate(result["accepted"], result["sent"])
    result["median_seconds_to_accept"] = None if not durations else int(round(median(durations)))
    return result


def _funnel_comparison(current, previous, *, include_terminal=True):
    keys = ["created", "sent", "accepted", "email_failed"]
    if include_terminal:
        keys.extend(["expired", "revoked"])
    result = {key: _change(current[key], previous[key]) for key in keys}
    result["send_to_accept_rate_pct"] = _nullable_change(
        current["send_to_accept_rate_pct"], previous["send_to_accept_rate_pct"]
    )
    result["median_seconds_to_accept"] = _nullable_change(
        current["median_seconds_to_accept"], previous["median_seconds_to_accept"]
    )
    return result


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
    current_funnel = _invite_funnel(start, end)
    previous_funnel = _invite_funnel(previous_start, start)
    current_owner_funnel = _invite_funnel(start, end, role="owner")
    previous_owner_funnel = _invite_funnel(previous_start, start, role="owner")
    engagement = rolling_engagement(end)
    activation = activation_overview(start, end, previous_start, observation_end=end)

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
            "engagement": engagement,
            "activation": activation,
            "onboarding": {
                "invites": _funnel_comparison(current_funnel, previous_funnel),
                "owner_invites": _funnel_comparison(
                    current_owner_funnel,
                    previous_owner_funnel,
                    include_terminal=False,
                ),
                "measurement": {
                    "cohort": "Invites with invite.created in the selected period; later funnel stages must also occur inside that same selected period.",
                    "opened_or_read": "not_measured",
                    "opened_or_read_reason": "No privacy-safe canonical open/read event exists; SMTP sent is not treated as a read receipt.",
                },
            },
            "timeseries": _daily_series(start, end),
            "definitions": {
                "active_user": "Authenticated user with at least one activity.foreground usage event in the selected period.",
                "active_family": "Family with at least one activity.foreground usage event in the selected period.",
                "verified_email_user": "User with a verified primary EmailIdentity.",
                "dau_wau_mau": "Rolling distinct users with activity.foreground in the preceding 1, 7 and 30 days, anchored at period.end; equal-length preceding windows are used for comparison when raw retention is sufficient.",
                "activation_v1": "New-account invite acceptance followed by canonical email verification and meaningful activity in the accepted family within 7 days; only mature cohort rows enter the rate denominator.",
                "invite_send_to_accept_rate": "Distinct created invites accepted in-period divided by distinct created invites with invite.sent in-period; null when no invite was sent.",
                "invite_median_seconds_to_accept": "Median elapsed seconds from invite.created to invite.accepted for accepted invites in the selected created-in-period cohort.",
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
