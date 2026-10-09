from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.utils import timezone
from rest_framework.decorators import api_view
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from .models import AutomationRule, Family, FamilyEvent, InboxItem, Routine, ShoppingList, Task, TaskList
from .serializers import FamilyEventSerializer, RoutineSerializer, ShoppingListSerializer, TaskListSerializer, TaskSerializer


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
        })

    now = timezone.now()
    tasks = Task.objects.filter(family=family, completed_at__isnull=True).select_related("task_list", "assignee").order_by("due_at", "-created_at")[:12]
    upcoming = FamilyEvent.objects.filter(family=family, starts_at__gte=now).order_by("starts_at")
    events = list(upcoming[:12])

    # Waste calendars often encode collection dates as all-day events at 00:00.
    # Keep today's collection visible for the whole local family day and always
    # include the next two collection dates even when many other events precede them.
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

    current_weather = FamilyEvent.objects.filter(family=family, type="weather.current").order_by("-starts_at", "-updated_at").first()
    if current_weather and all(event.id != current_weather.id for event in events):
        events = [current_weather, *events]
    routines = Routine.objects.filter(family=family, active=True).prefetch_related("logs")[:8]
    shopping = ShoppingList.objects.filter(family=family, archived=False).prefetch_related("items").order_by("sort_order", "created_at")[:8]
    task_lists = TaskList.objects.filter(family=family, archived=False).prefetch_related("tasks")[:12]
    inbox_count = InboxItem.objects.filter(family=family, status="new").count()
    automation_count = AutomationRule.objects.filter(family=family, enabled=True).count()
    return Response({
        "family": str(family.id),
        "tasks": TaskSerializer(tasks, many=True).data,
        "task_lists": TaskListSerializer(task_lists, many=True).data,
        "events": FamilyEventSerializer(events, many=True).data,
        "routines": RoutineSerializer(routines, many=True).data,
        "shopping_lists": ShoppingListSerializer(shopping, many=True).data,
        "inbox_count": inbox_count,
        "automation_count": automation_count,
    })