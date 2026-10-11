from __future__ import annotations

from collections import defaultdict
from datetime import timedelta
from statistics import median

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db.models import Count, Q

from .models import AuditEvent, UsageEvent


ACTIVATION_WINDOW_DAYS = 7
NEW_ACCOUNT_ACCEPT_GRACE = timedelta(hours=1)
# Set to the actual merge instant of the canonical auth.email.verified emitter before
# this slice is opened for review. Until then activation stays fail-closed.
EMAIL_VERIFICATION_TELEMETRY_START = None


def _rate(numerator, denominator):
    return None if denominator in (None, 0) or numerator is None else round((numerator / denominator) * 100, 1)


def _nullable_change(current, previous):
    delta = None if current is None or previous is None else current - previous
    percentage = None
    if current is not None and previous not in (None, 0):
        percentage = round(((current - previous) / previous) * 100, 1)
    return {"value": current, "previous": previous, "delta": delta, "change_pct": percentage}


def _usage_retention_days():
    return max(0, int(getattr(settings, "TELEMETRY_USAGE_RETENTION_DAYS", 60)))


def _audit_retention_days():
    return max(0, int(getattr(settings, "TELEMETRY_AUDIT_RETENTION_DAYS", 180)))


def _rolling_aggregate(end):
    activity = UsageEvent.objects.filter(event_key="activity.foreground", occurred_at__lt=end)
    filters = {}
    for days in (1, 7, 30):
        current_start = end - timedelta(days=days)
        previous_start = current_start - timedelta(days=days)
        filters[f"users_{days}d"] = Count(
            "user_id",
            distinct=True,
            filter=Q(occurred_at__gte=current_start, occurred_at__lt=end),
        )
        filters[f"users_prev_{days}d"] = Count(
            "user_id",
            distinct=True,
            filter=Q(occurred_at__gte=previous_start, occurred_at__lt=current_start),
        )
    for days in (7, 30):
        current_start = end - timedelta(days=days)
        previous_start = current_start - timedelta(days=days)
        filters[f"families_{days}d"] = Count(
            "family_id",
            distinct=True,
            filter=Q(occurred_at__gte=current_start, occurred_at__lt=end),
        )
        filters[f"families_prev_{days}d"] = Count(
            "family_id",
            distinct=True,
            filter=Q(occurred_at__gte=previous_start, occurred_at__lt=current_start),
        )
    return activity.aggregate(**filters)


def _rolling_metric(values, end, *, days, key):
    retention_days = _usage_retention_days()
    retention_cutoff = end - timedelta(days=retention_days)
    current_start = end - timedelta(days=days)
    previous_start = current_start - timedelta(days=days)
    current_complete = current_start >= retention_cutoff
    previous_complete = previous_start >= retention_cutoff

    current = values[f"{key}_{days}d"] if current_complete else None
    previous = values[f"{key}_prev_{days}d"] if previous_complete else None
    result = _nullable_change(current, previous)
    result.update(
        {
            "window_days": days,
            "coverage": {
                "current_complete": current_complete,
                "comparison_complete": previous_complete,
                "raw_usage_retention_days": retention_days,
            },
        }
    )
    return result


def rolling_engagement(end):
    """Fixed rolling engagement windows anchored at the overview response end."""
    values = _rolling_aggregate(end)
    return {
        "dau": _rolling_metric(values, end, days=1, key="users"),
        "wau": _rolling_metric(values, end, days=7, key="users"),
        "mau": _rolling_metric(values, end, days=30, key="users"),
        "active_families_7d": _rolling_metric(values, end, days=7, key="families"),
        "active_families_30d": _rolling_metric(values, end, days=30, key="families"),
        "measurement": {
            "anchor": "period.end",
            "source": "distinct activity.foreground raw telemetry",
            "query_shape": "single conditional aggregate query for 1d/7d/30d current and comparison windows",
            "privacy": "aggregate distinct counts only; no family content or identifiers are serialized",
        },
    }


def _coverage(cohort_start, cohort_end, observation_end):
    reasons = []
    if EMAIL_VERIFICATION_TELEMETRY_START is None:
        return {
            "available": False,
            "complete": False,
            "selected_start": cohort_start,
            "selected_end": cohort_end,
            "effective_start": None,
            "reasons": ["email_verification_instrumentation_start_not_set"],
            "raw_usage_retention_days": _usage_retention_days(),
            "raw_audit_retention_days": _audit_retention_days(),
        }

    raw_days = min(_usage_retention_days(), _audit_retention_days())
    raw_cutoff = observation_end - timedelta(days=raw_days)
    effective_start = max(cohort_start, EMAIL_VERIFICATION_TELEMETRY_START, raw_cutoff)
    if EMAIL_VERIFICATION_TELEMETRY_START > cohort_start:
        reasons.append("email_verification_forward_only")
    if raw_cutoff > cohort_start:
        reasons.append("raw_event_retention")
    available = effective_start < cohort_end
    return {
        "available": available,
        "complete": available and effective_start == cohort_start,
        "selected_start": cohort_start,
        "selected_end": cohort_end,
        "effective_start": effective_start if available else None,
        "reasons": reasons if available else reasons or ["no_measurable_cohort_window"],
        "raw_usage_retention_days": _usage_retention_days(),
        "raw_audit_retention_days": _audit_retention_days(),
    }


def _empty_activation(coverage):
    return {
        "available": False,
        "coverage": coverage,
        "accepted_new_accounts": None,
        "mature_cohort": None,
        "pending_maturity": None,
        "email_verified_within_7d": None,
        "meaningful_activity_within_7d": None,
        "activated_within_7d": None,
        "activation_rate_pct": None,
        "median_seconds_to_activation": None,
        "excluded_existing_accounts": None,
    }


def _activation_metrics(cohort_start, cohort_end, *, observation_end):
    coverage = _coverage(cohort_start, cohort_end, observation_end)
    if not coverage["available"]:
        return _empty_activation(coverage)

    accepted_rows = list(
        AuditEvent.objects.filter(
            event_key="invite.accepted",
            target_type="invite",
            actor__isnull=False,
            family__isnull=False,
            occurred_at__gte=coverage["effective_start"],
            occurred_at__lt=cohort_end,
        )
        .values("target_id", "actor_id", "family_id", "occurred_at")
        .order_by("occurred_at", "id")
    )

    # Audit is append-only, but dedupe by invite target defensively so accidental
    # duplicate instrumentation cannot inflate a cohort.
    distinct_accepts = []
    seen_invites = set()
    for row in accepted_rows:
        if row["target_id"] in seen_invites:
            continue
        seen_invites.add(row["target_id"])
        distinct_accepts.append(row)

    user_ids = {row["actor_id"] for row in distinct_accepts}
    joined_at = dict(
        get_user_model().objects.filter(pk__in=user_ids).values_list("pk", "date_joined")
    )

    cohort = []
    excluded_existing = 0
    for row in distinct_accepts:
        joined = joined_at.get(row["actor_id"])
        accepted = row["occurred_at"]
        if joined is None or joined > accepted or joined < accepted - NEW_ACCOUNT_ACCEPT_GRACE:
            excluded_existing += 1
            continue
        cohort.append(
            {
                **row,
                "deadline": accepted + timedelta(days=ACTIVATION_WINDOW_DAYS),
            }
        )

    mature = [row for row in cohort if row["deadline"] <= observation_end]
    if not mature:
        return {
            "available": True,
            "coverage": coverage,
            "accepted_new_accounts": len(cohort),
            "mature_cohort": 0,
            "pending_maturity": len(cohort),
            "email_verified_within_7d": 0,
            "meaningful_activity_within_7d": 0,
            "activated_within_7d": 0,
            "activation_rate_pct": None,
            "median_seconds_to_activation": None,
            "excluded_existing_accounts": excluded_existing,
        }

    mature_user_ids = {row["actor_id"] for row in mature}
    mature_family_ids = {row["family_id"] for row in mature}
    first_accept = min(row["occurred_at"] for row in mature)
    last_deadline = max(row["deadline"] for row in mature)

    verification_times = defaultdict(list)
    for row in (
        AuditEvent.objects.filter(
            event_key="auth.email.verified",
            actor_id__in=mature_user_ids,
            target_type="user",
            occurred_at__gte=first_accept,
            occurred_at__lte=last_deadline,
        )
        .values("actor_id", "occurred_at")
        .order_by("actor_id", "occurred_at")
    ):
        verification_times[row["actor_id"]].append(row["occurred_at"])

    activity_times = defaultdict(list)
    for row in (
        UsageEvent.objects.filter(
            event_key="activity.foreground",
            user_id__in=mature_user_ids,
            family_id__in=mature_family_ids,
            occurred_at__gte=first_accept,
            occurred_at__lte=last_deadline,
        )
        .values("user_id", "family_id", "occurred_at")
        .order_by("user_id", "family_id", "occurred_at")
    ):
        activity_times[(row["user_id"], row["family_id"])].append(row["occurred_at"])

    verified_count = 0
    activity_count = 0
    activated_count = 0
    activation_durations = []
    for row in mature:
        accepted = row["occurred_at"]
        deadline = row["deadline"]
        verified_at = next(
            (value for value in verification_times[row["actor_id"]] if accepted <= value <= deadline),
            None,
        )
        active_at = next(
            (
                value
                for value in activity_times[(row["actor_id"], row["family_id"])]
                if accepted <= value <= deadline
            ),
            None,
        )
        if verified_at is not None:
            verified_count += 1
        if active_at is not None:
            activity_count += 1
        if verified_at is not None and active_at is not None:
            activated_count += 1
            activation_durations.append(int((max(verified_at, active_at) - accepted).total_seconds()))

    return {
        "available": True,
        "coverage": coverage,
        "accepted_new_accounts": len(cohort),
        "mature_cohort": len(mature),
        "pending_maturity": len(cohort) - len(mature),
        "email_verified_within_7d": verified_count,
        "meaningful_activity_within_7d": activity_count,
        "activated_within_7d": activated_count,
        "activation_rate_pct": _rate(activated_count, len(mature)),
        "median_seconds_to_activation": (
            None if not activation_durations else int(round(median(activation_durations)))
        ),
        "excluded_existing_accounts": excluded_existing,
    }


def activation_overview(start, end, previous_start, *, observation_end=None):
    observation_end = observation_end or end
    current = _activation_metrics(start, end, observation_end=observation_end)
    previous = _activation_metrics(previous_start, start, observation_end=observation_end)
    return {
        "definition": {
            "version": "invite_new_account_v1",
            "cohort": "invite.accepted events for accounts created no more than one hour before acceptance",
            "email_verification": "auth.email.verified by the same user within 7 days after acceptance",
            "meaningful_activity": "activity.foreground by the same user in the accepted family within 7 days",
            "activated": "both email verification and meaningful activity completed within 7 days",
            "maturity": "only cohort rows whose full 7-day observation window has elapsed enter the activation-rate denominator",
        },
        "current": current,
        "previous": previous,
        "comparison": {
            "activated_within_7d": _nullable_change(
                current["activated_within_7d"], previous["activated_within_7d"]
            ),
            "activation_rate_pct": _nullable_change(
                current["activation_rate_pct"], previous["activation_rate_pct"]
            ),
            "median_seconds_to_activation": _nullable_change(
                current["median_seconds_to_activation"], previous["median_seconds_to_activation"]
            ),
        },
        "measurement": {
            "forward_only_email_verification": True,
            "private_content": "not_queried",
            "identifiers_in_response": False,
        },
    }
