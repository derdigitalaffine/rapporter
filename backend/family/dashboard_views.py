from django.utils import timezone
from rest_framework.decorators import api_view
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from .models import AutomationRule, Family, FamilyEvent, InboxItem, Routine, ShoppingList, Task, TaskList
from .serializers import FamilyEventSerializer, RoutineSerializer, ShoppingListSerializer, TaskListSerializer, TaskSerializer
from .weather_contract import WEATHER_DATA_TYPES, build_weather_contract


def _active_family(request):
    family_id = request.query_params.get("family")
    families = Family.objects.filter(memberships__user=request.user).distinct()
    if family_id:
        family = families.filter(id=family_id).first()
        if not family:
            raise PermissionDenied("Familie ist für diesen Benutzer nicht verfügbar.")
        return family
    return families.first()


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
            "weather": None,
        })

    now = timezone.now()
    tasks = Task.objects.filter(family=family, completed_at__isnull=True).select_related("task_list", "assignee").order_by("due_at", "-created_at")[:12]
    events = FamilyEvent.objects.filter(family=family, starts_at__gte=now).exclude(type__in=WEATHER_DATA_TYPES).order_by("starts_at")[:12]
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
        "weather": build_weather_contract(family),
    })
