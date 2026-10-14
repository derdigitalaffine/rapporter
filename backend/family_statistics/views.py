"""Bounded rollup reads; every endpoint intersects family, role and capability."""
from collections import defaultdict
from datetime import date, datetime, time, timedelta
from uuid import UUID
from django.db.models import Count, Max, Q, Prefetch
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from entitlements.services import require_capability, resolve_entitlements
from entitlements.models import CapabilityDefinition
from family.models import Family, Membership, Task, Routine, RoutineLog
from .models import FamilyContributionDaily as Daily, FamilyContributionEvent as Event
from .services import zone_for

DOMAINS = {"task": "todo", "routine": "todo", "shopping": "shopping", "calendar": "calendar"}
EXECUTION = {"completed", "item_purchased"}
PLANNING = {"created", "item_added", "list_created", "event_created"}


def context(request):
    try:
        family_id = UUID(request.query_params.get("family", ""))
    except (ValueError, TypeError):
        raise ValidationError({"family": "A valid family ID is required."})
    membership = get_object_or_404(Membership.objects.select_related("family"), family_id=family_id,
        user=request.user, family__status=Family.Status.ACTIVE)
    if membership.role == "guest":
        raise PermissionDenied("Statistics is unavailable to guests.")
    require_capability(request.user, membership.family, "statistics")
    capabilities = set(resolve_entitlements(membership.family).capabilities)
    domains = [domain for domain, capability in DOMAINS.items() if capability in capabilities and domain != "calendar"]
    family = membership.family
    zone = zone_for(family)
    today = timezone.now().astimezone(zone).date()
    try:
        if request.query_params.get("from") or request.query_params.get("to"):
            start = date.fromisoformat(request.query_params.get("from", ""))
            end = date.fromisoformat(request.query_params.get("to", ""))
        else:
            days = {"7d": 7, "30d": 30, "90d": 90, "365d": 365}[request.query_params.get("range", "30d")]
            end, start = today, today - timedelta(days=days - 1)
    except (ValueError, KeyError):
        raise ValidationError({"range": "Choose 7d, 30d, 90d, 365d or an ISO date range."})
    if start > end or (end - start).days >= 365 or end > today:
        raise ValidationError({"range": "Choose up to 365 days ending no later than today."})
    member_id = request.query_params.get("member")
    if membership.role == "child":
        member_id = str(membership.pk)
    if member_id:
        try:
            selected = get_object_or_404(Membership, pk=UUID(member_id), family=family)
        except ValueError:
            raise ValidationError({"member": "Invalid membership ID."})
        if membership.role not in {"owner", "adult"} and selected.pk != membership.pk:
            raise PermissionDenied("Only your own named contributions are available.")
        member_id = str(selected.pk)
    domain = request.query_params.get("domain")
    if domain and domain not in domains:
        raise PermissionDenied("Domain is unavailable.")
    return family, membership, domains, start, end, member_id, domain


def totals(rows):
    result = {"completed": 0, "organized": 0, "reopened": 0, "effort_minutes": 0,
              "effort_coverage_count": 0, "task_completions": 0, "attributed": 0}
    for row in rows:
        count = row["count"]
        verb = row["action"]
        result["completed"] += count if verb in EXECUTION else 0
        result["organized"] += count if verb in PLANNING else 0
        result["reopened"] += count if verb == "reopened" else 0
        if verb in EXECUTION:
            result["attributed"] += count if row["actor_membership_id"] else 0
        if row["domain"] == "task" and verb == "completed":
            result["task_completions"] += count
            result["effort_minutes"] += row["effort_minutes_sum"]
            result["effort_coverage_count"] += row["effort_coverage_count"]
    result["effort_coverage"] = round(100 * result["effort_coverage_count"] / result["task_completions"], 1) if result["task_completions"] else None
    result["actor_coverage"] = round(100 * result["attributed"] / result["completed"], 1) if result["completed"] else None
    return result


def read_rows(family, domains, start, end, member_id=None, domain=None):
    rows = Daily.objects.filter(family=family, local_date__gte=start, local_date__lte=end, domain__in=domains)
    if member_id:
        rows = rows.filter(actor_membership_id=member_id)
    if domain:
        rows = rows.filter(domain=domain)
    return list(rows.values("local_date", "actor_membership_id", "domain", "action", "count", "effort_minutes_sum", "effort_coverage_count"))


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def overview(request):
    family, membership, domains, start, end, selected, domain = context(request)
    days = (end - start).days + 1
    rows = read_rows(family, domains, start - timedelta(days=days), end, selected, domain)
    current = [row for row in rows if row["local_date"] >= start]
    previous = totals([row for row in rows if row["local_date"] < start])
    summary = totals(current)
    visible_members = Membership.objects.filter(family=family).select_related("user").order_by("created_at", "id")
    adults = membership.role in {"owner", "adult"}
    if not adults:
        visible_members = visible_members.filter(pk=membership.pk)
    members = []
    for member in visible_members:
        stats = totals([row for row in current if row["actor_membership_id"] == member.pk])
        members.append({"id": str(member.id), "name": member.display_name or member.user.get_full_name() or member.user.username,
            "self": member.pk == membership.pk, **stats,
            "domains": [{"key": key, **totals([row for row in current if row["actor_membership_id"] == member.pk and row["domain"] == key])} for key in domains]})
    series = defaultdict(list)
    for row in current:
        series[row["local_date"]].append(row)
    timeseries = [{"date": (start + timedelta(days=i)).isoformat(), **totals(series[start + timedelta(days=i)])} for i in range(days)]
    breakdown = [{"key": key, **totals([row for row in current if row["domain"] == key]), "detail": f"/api/statistics/{ {'task':'tasks','routine':'routines','shopping':'shopping'}[key] }/"} for key in domains if not domain or key == domain]
    # Current backlog is a snapshot, not an activity rate or assignee contribution.
    tasks = Task.objects.filter(family=family, birthday_context__isnull=True, hidden_from_user__isnull=True)
    overdue = tasks.filter(completed_at__isnull=True, due_at__lt=timezone.now()).count() if "task" in domains else None
    if membership.role == "child":
        overdue = tasks.filter(assignee=request.user, completed_at__isnull=True, due_at__lt=timezone.now()).count() if "task" in domains else None
    insights = []
    if previous["completed"]:
        insights.append({"key": "change", "value": round(100 * (summary["completed"] - previous["completed"]) / previous["completed"], 1), "formula": "(current - previous) / previous × 100", "domain": None})
    if summary["actor_coverage"] is not None and summary["actor_coverage"] < 100:
        insights.append({"key": "coverage", "value": summary["actor_coverage"], "formula": "attributed execution / all execution × 100", "domain": "task"})
    if adults:
        shoppers = sum(1 for member in members if any(d["key"] == "shopping" and d["completed"] for d in member["domains"]))
        if shoppers:
            insights.append({"key": "shopping_members", "value": shoppers, "formula": "members with at least one visible purchase", "domain": "shopping"})
    return Response({"meta": {"family": str(family.id), "from": start, "to": end, "timezone": family.timezone,
        "generated_at": timezone.now(), "role": membership.role, "can_compare_members": adults,
        "can_export": adults, "scope": "self" if membership.role == "child" else "family",
        "actor_coverage": summary["actor_coverage"], "effort_coverage": summary["effort_coverage"],
        "historical_attribution": "only_proven_actors", "attribution_since": CapabilityDefinition.objects.filter(key="statistics").values_list("created_at", flat=True).first(), "routine_due_coverage": "unavailable",
        "routine_rate": None, "available_domains": domains},
        "summary": {**summary, "overdue_now": overdue}, "previous": previous,
        "members": members, "domains": breakdown, "timeseries": timeseries, "insights": insights})


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def detail(request, domain):
    family, membership, domains, start, end, selected, domain_filter = context(request)
    key = {"tasks": "task", "routines": "routine", "shopping": "shopping"}.get(domain)
    if key not in domains:
        raise PermissionDenied("Domain is unavailable.")
    zone = zone_for(family)
    start_time = datetime.combine(start, time.min, tzinfo=zone)
    end_time = datetime.combine(end + timedelta(days=1), time.min, tzinfo=zone)
    events = Event.objects.filter(family=family, domain=key, occurred_at__gte=start_time, occurred_at__lt=end_time)
    if selected:
        events = events.filter(actor_membership_id=selected)
    # Only adults receive others' identifiers. Teen aggregate remains anonymous.
    adults = membership.role in {"owner", "adult"}
    try:
        page = int(request.query_params.get("page", "1"))
        if not 1 <= page <= 10000:
            raise ValueError()
    except ValueError:
        raise ValidationError({"page": "Invalid page."})
    count = events.count()
    rows = list(events.order_by("-occurred_at", "-id")[(page - 1) * 50:page * 50])
    result = [{"id": str(row.id), "action": row.action, "occurred_at": row.occurred_at,
        "member": str(row.actor_membership_id) if row.actor_membership_id and (adults or row.actor_membership_id == membership.pk) else None,
        "effort_minutes": row.effort_minutes,
        "entity": str(row.entity_id) if row.entity_id else None,
        "page": {"task": "tasks", "routine": "routines", "shopping": "shopping"}[key]} for row in rows]
    extra = {"summary": totals(read_rows(family, domains, start, end, selected, key))}
    if key == "routine":
        # No due denominator is invented for adaptive/historically changing schedules.
        routines = Routine.objects.filter(family=family).select_related("family").prefetch_related(Prefetch("logs", queryset=RoutineLog.objects.only("id", "routine_id", "done_at").order_by("-done_at")[:64], to_attr="_statistics_logs")).order_by("created_at", "id")
        if membership.role == "child" or selected:
            routines = routines.filter(pk__in=events.values("entity_id"))
        extra["active_routines"] = routines.filter(active=True).count()
        groups = {row["entity_id"]: row for row in events.filter(action="completed").values("entity_id").annotate(total=Count("id"), latest=Max("occurred_at"))}
        extra["routines"] = [{"id": str(row.id), "name": row.name, "active": row.active,
            "interval_days": row.suggested_interval_days,
            "completed": groups.get(row.pk, {}).get("total", 0),
            "last_completed": groups.get(row.pk, {}).get("latest"),
            "next_due": current_prediction(row).get("expected_at"), "due_basis": "canonical_routine_prediction",
            "href": f"?page=routines&family={family.id}&routine={row.id}"} for row in routines[:100]]
        extra["due_count"] = None
        extra["completion_rate"] = None
    return Response({"domain": key, "count": count, "page": page, "page_size": 50,
        "has_next": page * 50 < count, "results": result, **extra})


def current_prediction(routine):
    from family.predictions import routine_prediction
    routine._prefetched_objects_cache["logs"] = routine._statistics_logs
    return routine_prediction(routine)
