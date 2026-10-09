from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.utils import timezone
from rest_framework.decorators import api_view
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from .birthdays import project
from .models import AutomationRule, Family, FamilyEvent, InboxItem, IntegrationSource, Routine, ShoppingList, Task, TaskList
from .serializers import FamilyEventSerializer, RoutineSerializer, ShoppingListSerializer, TaskListSerializer, TaskSerializer
from .weather_service import weather_payload


def _active_family(request):
    family_id = request.query_params.get("family")
    families = Family.objects.filter(memberships__user=request.user).distinct()
    if family_id:
        family = families.filter(id=family_id).first()
        if not family:
            raise PermissionDenied("Familie ist für diesen Benutzer nicht verfügbar.")
        return family
    return families.first()


def _family_day_start(family, now):
    try:
        family_timezone = ZoneInfo(family.timezone)
    except (ZoneInfoNotFoundError, ValueError, TypeError):
        family_timezone = timezone.get_current_timezone()
    local_now = now.astimezone(family_timezone)
    return local_now.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(now.tzinfo)


@api_view(["GET"])
def dashboard(request):
    family = _active_family(request)
    if not family:
        return Response({
            "tasks": [],
            "task_lists": [],
            "events": [],
            "routines": [],
            "shopping_lists": [],
            "inbox_count": 0,
            "automation_count": 0,
            "integration_count": 0,
            "enabled_integration_count": 0,
            "weather": {"current": None, "days": [], "alerts": []},
        })

    now = timezone.now()
    tasks = Task.objects.exclude(hidden_from_user=request.user).filter(
        family=family,
        completed_at__isnull=True,
    ).select_related("task_list", "assignee").order_by("due_at", "-created_at")[:12]

    upcoming = FamilyEvent.objects.filter(
        family=family,
        starts_at__gte=now,
    ).exclude(type__in=["weather.current", "weather.forecast"]).order_by("starts_at")
    events = list(upcoming[:12])

    # Waste calendars commonly encode collection dates as all-day events at
    # midnight. Keep today's collection for the complete local family day and
    # guarantee that the next two collection dates reach the Today dashboard,
    # even when twelve other calendar events occur first.
    waste_floor = _family_day_start(family, now)
    next_waste = list(
        FamilyEvent.objects.filter(
            family=family,
            type__startswith="waste.",
            starts_at__gte=waste_floor,
        ).order_by("starts_at")[:2]
    )
    known_ids = {event.id for event in events}
    events.extend(event for event in next_waste if event.id not in known_ids)
    events.sort(key=lambda event: event.starts_at or now)

    routines = Routine.objects.filter(family=family, active=True).prefetch_related("logs", "reminder_states__membership")
    shopping = ShoppingList.objects.filter(family=family, archived=False).prefetch_related("items").order_by("sort_order", "created_at")[:8]
    task_lists = TaskList.objects.filter(family=family, archived=False).prefetch_related("tasks")[:12]
    integrations = IntegrationSource.objects.filter(family=family)

    return Response({
        "family": str(family.id),
        "tasks": TaskSerializer(tasks, many=True).data,
        "task_lists": TaskListSerializer(task_lists, many=True, context={"request":request}).data,
        "events": FamilyEventSerializer(events, many=True).data,
        "routines": sorted(RoutineSerializer(routines, many=True, context={"request":request}).data, key=lambda row:(0 if row["prediction"]["status"] in {"due","overdue"} else 1,str(row["prediction"]["expected_at"] or "9999")))[:8],
        "shopping_lists": ShoppingListSerializer(shopping, many=True, context={"request":request}).data,
        "inbox_count": InboxItem.objects.filter(family=family, status="new").count(),
        "automation_count": AutomationRule.objects.filter(family=family, enabled=True).count(),
        "integration_count": integrations.count(),
        "enabled_integration_count": integrations.filter(enabled=True).count(),
        "birthdays": [row for row in project(family,request.user) if row["days_until"]<=21 and (row["days_until"]<=7 or row.get("gift_status") not in {"ready","given"})],
        "weather": weather_payload(family),
    })
