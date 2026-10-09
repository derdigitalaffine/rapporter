from collections import defaultdict
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Q
from django.utils import timezone
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from .automation import RULE_TEMPLATES, run_rule
from .integrations import INTEGRATION_CATALOG, sync_source
from .models import Family, Membership, TaskList, Task, ShoppingList, ShoppingItem, Routine, RoutineLog, IntegrationSource, FamilyEvent, InboxItem, AutomationRule
from .serializers import FamilySerializer, TaskListSerializer, TaskSerializer, ShoppingListSerializer, ShoppingItemSerializer, RoutineSerializer, RoutineLogSerializer, IntegrationSourceSerializer, FamilyEventSerializer, InboxItemSerializer, AutomationRuleSerializer


def family_ids(user):
    return Membership.objects.filter(user=user).values_list("family_id", flat=True)


def can_manage_settings(user, family):
    return Membership.objects.filter(family=family, user=user, role__in=[Membership.Role.OWNER, Membership.Role.ADULT]).exists()


def _family_for_request(request):
    family_id = request.query_params.get("family") or request.data.get("family")
    if family_id:
        return Family.objects.filter(id=family_id, memberships__user=request.user).first()
    return Family.objects.filter(memberships__user=request.user).first()


def _smart_history(rows, query, fields, limit=12):
    query = (query or "").strip().casefold()
    grouped = {}
    now = timezone.now()
    for row in rows:
        key = (row.name or "").strip().casefold()
        if not key or (query and query not in key):
            continue
        entry = grouped.setdefault(key, {"name": row.name, "count": 0, "last_used": row.updated_at, "values": defaultdict(lambda: defaultdict(int))})
        entry["count"] += 1
        if row.updated_at and row.updated_at > entry["last_used"]:
            entry["last_used"] = row.updated_at
            entry["name"] = row.name
        for field in fields:
            value = getattr(row, field, None)
            if value not in (None, "", [], {}):
                try:
                    hash(value)
                    entry["values"][field][value] += 1
                except TypeError:
                    pass
    result = []
    for entry in grouped.values():
        age_days = max(0, (now - entry["last_used"]).days) if entry["last_used"] else 999
        score = entry["count"] * 20 + max(0, 30 - min(age_days, 30))
        item = {"name": entry["name"], "count": entry["count"], "last_used": entry["last_used"], "score": score}
        for field, choices in entry["values"].items():
            if choices:
                item[field] = max(choices, key=choices.get)
        result.append(item)
    return sorted(result, key=lambda x: (-x["score"], x["name"].casefold()))[:limit]


class FamilyScopedViewSet(viewsets.ModelViewSet):
    family_lookup = "family_id"

    def get_queryset(self):
        queryset = self.queryset.filter(**{f"{self.family_lookup}__in": family_ids(self.request.user)})
        if self.queryset.model is Task:
            queryset = queryset.exclude(hidden_from_user=self.request.user)
        return queryset

    def perform_create(self, serializer):
        family = serializer.validated_data.get("family")
        if family and not Membership.objects.filter(family=family, user=self.request.user).exists():
            raise PermissionDenied()
        serializer.save()


class FamilyViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = FamilySerializer
    permission_classes = [permissions.IsAuthenticated]
    def get_queryset(self):
        return Family.objects.filter(memberships__user=self.request.user).distinct()


class TaskListViewSet(FamilyScopedViewSet):
    queryset = TaskList.objects.prefetch_related("tasks", "workflow_columns").all()
    serializer_class = TaskListSerializer

    def perform_create(self, serializer):
        family = serializer.validated_data["family"]
        if not Membership.objects.filter(family=family, user=self.request.user).exists():
            raise PermissionDenied()
        serializer.save()

    @action(detail=True, methods=["get", "post"], url_path="workflow-columns")
    def workflow_columns(self, request, pk=None):
        from .workflow_views import list_columns
        return list_columns(self, request)


class TaskViewSet(FamilyScopedViewSet):
    queryset = Task.objects.select_related("task_list", "assignee", "workflow_column").all().order_by("completed_at", "due_at", "-created_at")
    serializer_class = TaskSerializer

    def perform_create(self, serializer):
        family = serializer.validated_data["family"]
        if not Membership.objects.filter(family=family, user=self.request.user).exists():
            raise PermissionDenied()
        task_list = serializer.validated_data.get("task_list")
        if task_list and task_list.family_id != family.id:
            raise PermissionDenied()
        if not task_list:
            task_list, _ = TaskList.objects.get_or_create(family=family, name="Allgemein", defaults={"icon": "list-check"})
        serializer.save(created_by=self.request.user, task_list=task_list)

    @action(detail=True, methods=["post"])
    def toggle(self, request, pk=None):
        from django.db import transaction
        with transaction.atomic():
            task = self.get_object()
            if task.task_list_id:
                TaskList.objects.select_for_update().get(pk=task.task_list_id)
            task.refresh_from_db()
            task.completed_at = None if task.completed_at else timezone.now()
            task.save(update_fields=["completed_at", "updated_at"])
        return Response(self.get_serializer(task).data)

    @action(detail=True, methods=["post"])
    def move(self, request, pk=None):
        from .models import TaskWorkflowColumn
        from .task_workflow import move_task
        from rest_framework.exceptions import ValidationError
        try:
            column = TaskWorkflowColumn.objects.get(pk=request.data.get("column_id"))
        except (TaskWorkflowColumn.DoesNotExist, ValueError, TypeError, DjangoValidationError):
            raise ValidationError({"column_id": "Invalid workflow column."})
        task = move_task(self.get_object(), column, request.data.get("before_task_id"))
        return Response(self.get_serializer(task).data)

    @action(detail=True, methods=["get"], url_path="status-history")
    def status_history(self, request, pk=None):
        rows = self.get_object().status_events.select_related("from_column", "to_column", "changed_by")
        page = self.paginate_queryset(rows)
        result = [{"id": str(row.id), "from": row.from_column.name if row.from_column else None, "to": row.to_column.name if row.to_column else None, "changed_by": row.changed_by.username if row.changed_by else "FamilyOS", "changed_at": row.created_at, "source": row.source} for row in page]
        return self.get_paginated_response(result)

    @action(detail=False, methods=["get"])
    def suggestions(self, request):
        family = _family_for_request(request)
        if not family:
            return Response([])
        rows = Task.objects.filter(family=family,birthday_context__isnull=True).order_by("-updated_at")[:600]
        return Response(_smart_history(rows, request.query_params.get("q"), ["notes", "priority", "estimate_minutes"], 10))


class ShoppingListViewSet(FamilyScopedViewSet):
    queryset = ShoppingList.objects.prefetch_related("items").all().order_by("sort_order", "created_at")
    serializer_class = ShoppingListSerializer


class ShoppingItemViewSet(viewsets.ModelViewSet):
    queryset = ShoppingItem.objects.select_related("shopping_list", "added_by").all()
    serializer_class = ShoppingItemSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return self.queryset.filter(shopping_list__family_id__in=family_ids(self.request.user)).exclude(hidden_from_user=self.request.user)

    def perform_create(self, serializer):
        shopping_list = serializer.validated_data["shopping_list"]
        if shopping_list.family_id not in set(family_ids(self.request.user)):
            raise PermissionDenied()
        serializer.save(added_by=self.request.user)

    def perform_update(self, serializer):
        item = serializer.instance
        checked = serializer.validated_data.get("checked", item.checked)
        if checked != item.checked:
            serializer.save(checked_at=timezone.now() if checked else None)
        else:
            serializer.save()

    @action(detail=True, methods=["post"])
    def toggle(self, request, pk=None):
        item = self.get_object()
        item.checked = not item.checked
        item.checked_at = timezone.now() if item.checked else None
        item.save(update_fields=["checked", "checked_at", "updated_at"])
        return Response(self.get_serializer(item).data)

    @action(detail=False, methods=["get"])
    def suggestions(self, request):
        family = _family_for_request(request)
        if not family:
            return Response([])
        rows = ShoppingItem.objects.filter(shopping_list__family=family).order_by("-updated_at")[:1000]
        return Response(_smart_history(rows, request.query_params.get("q"), ["quantity", "category", "aisle", "note"], 12))


class RoutineViewSet(FamilyScopedViewSet):
    queryset = Routine.objects.select_related("family").prefetch_related("logs__done_by", "reminder_states__membership").all()
    serializer_class = RoutineSerializer

    def get_queryset(self):
        rows = super().get_queryset()
        family = self.request.query_params.get("family")
        return rows.filter(family_id=family) if family else rows

    @action(detail=True, methods=["post"])
    def done(self, request, pk=None):
        from django.db import transaction
        from uuid import UUID
        from rest_framework.exceptions import ValidationError
        request_id = request.data.get("request_id")
        try:
            request_id = UUID(str(request_id)) if request_id else None
        except ValueError:
            raise ValidationError({"request_id": "Invalid request ID."})
        note = str(request.data.get("note", ""))
        if len(note)>240:
            raise ValidationError({"note": "Maximum 240 characters."})
        with transaction.atomic():
            routine = self.get_object()
            Routine.objects.select_for_update().get(pk=routine.pk)
            if not routine.active:
                raise ValidationError({"routine": "Reactivate this routine before recording it."})
            log = routine.logs.filter(request_id=request_id).first() if request_id else None
            created = log is None
            if log is None:
                log = RoutineLog.objects.create(routine=routine, done_at=timezone.now(), done_by=request.user, note=note, request_id=request_id)
            elif log.done_by_id!=request.user.id:
                raise PermissionDenied()
        return Response(RoutineLogSerializer(log).data, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)

    @action(detail=True, methods=["get"])
    def history(self, request, pk=None):
        rows = self.get_object().logs.select_related("done_by").all()
        page = self.paginate_queryset(rows)
        return self.get_paginated_response(RoutineLogSerializer(page, many=True).data)

    @action(detail=True, methods=["delete"], url_path="logs/(?P<log_id>[^/.]+)")
    def remove_log(self, request, pk=None, log_id=None):
        from django.shortcuts import get_object_or_404
        routine = self.get_object()
        log = get_object_or_404(routine.logs, pk=log_id)
        if log.done_by_id!=request.user.id and not can_manage_settings(request.user,routine.family):
            raise PermissionDenied()
        log.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["post"])
    def snooze(self, request, pk=None):
        from datetime import timedelta
        from rest_framework.exceptions import ValidationError
        from .models import RoutineReminderState
        routine = self.get_object()
        hours = request.data.get("hours",24)
        if not isinstance(hours,int) or isinstance(hours,bool) or not 0<=hours<=168:
            raise ValidationError({"hours":"Choose 0–168 hours."})
        membership = Membership.objects.get(family=routine.family,user=request.user)
        state,_ = RoutineReminderState.objects.get_or_create(routine=routine,membership=membership)
        state.snoozed_until = timezone.now()+timedelta(hours=hours) if hours else None
        state.save(update_fields=["snoozed_until","updated_at"])
        return Response({"snoozed_until":state.snoozed_until})


class IntegrationSourceViewSet(FamilyScopedViewSet):
    queryset = IntegrationSource.objects.all().order_by("kind", "name")
    serializer_class = IntegrationSourceSerializer

    def perform_create(self, serializer):
        family = serializer.validated_data["family"]
        if not can_manage_settings(self.request.user, family):
            raise PermissionDenied("Nur Erwachsene/Owner können Integrationen verwalten.")
        serializer.save()

    def perform_update(self, serializer):
        source = self.get_object()
        if not can_manage_settings(self.request.user, source.family):
            raise PermissionDenied("Nur Erwachsene/Owner können Integrationen verwalten.")
        serializer.save()

    def perform_destroy(self, instance):
        if not can_manage_settings(self.request.user, instance.family):
            raise PermissionDenied("Nur Erwachsene/Owner können Integrationen verwalten.")
        instance.delete()

    @action(detail=False, methods=["get"])
    def catalog(self, request):
        return Response(INTEGRATION_CATALOG)

    @action(detail=False, methods=["post"])
    def connect(self, request):
        family = Family.objects.filter(id=request.data.get("family"), memberships__user=request.user).first()
        if not family or not can_manage_settings(request.user, family):
            raise PermissionDenied("Nur Erwachsene/Owner können Integrationen verwalten.")
        item = next((x for x in INTEGRATION_CATALOG if x["id"] == request.data.get("catalog_id")), None)
        if not item:
            return Response({"detail": "Unbekannte Integration."}, status=status.HTTP_400_BAD_REQUEST)
        values = dict(request.data.get("values") or {})
        endpoint = values.pop("endpoint", "")
        source = IntegrationSource.objects.create(family=family, kind=item["kind"], name=item["name"], endpoint=endpoint, config={**item.get("defaults", {}), **values}, enabled=True)
        try:
            count = sync_source(source)
        except Exception as exc:
            source.delete()
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"source": self.get_serializer(source).data, "synced": count}, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def sync(self, request, pk=None):
        source = self.get_object()
        try:
            count = sync_source(source)
        except Exception as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"synced": count, "last_synced_at": source.last_synced_at})

    @action(detail=False, methods=["post"])
    def sync_all(self, request):
        total, errors = 0, []
        for source in self.get_queryset().filter(enabled=True):
            try:
                total += sync_source(source)
            except Exception as exc:
                errors.append({"id": str(source.id), "name": source.name, "detail": str(exc)})
        return Response({"synced": total, "errors": errors})


class AutomationRuleViewSet(FamilyScopedViewSet):
    queryset = AutomationRule.objects.prefetch_related("executions").all().order_by("-enabled", "name")
    serializer_class = AutomationRuleSerializer

    def perform_create(self, serializer):
        family = serializer.validated_data["family"]
        if not can_manage_settings(self.request.user, family):
            raise PermissionDenied("Nur Erwachsene/Owner können Regeln verwalten.")
        serializer.save(created_by=self.request.user)

    def perform_update(self, serializer):
        rule = self.get_object()
        if not can_manage_settings(self.request.user, rule.family):
            raise PermissionDenied("Nur Erwachsene/Owner können Regeln verwalten.")
        serializer.save()

    def perform_destroy(self, instance):
        if not can_manage_settings(self.request.user, instance.family):
            raise PermissionDenied("Nur Erwachsene/Owner können Regeln verwalten.")
        instance.delete()

    @action(detail=False, methods=["get"])
    def templates(self, request):
        return Response(RULE_TEMPLATES)

    @action(detail=False, methods=["post"])
    def from_template(self, request):
        family = Family.objects.filter(id=request.data.get("family"), memberships__user=request.user).first()
        if not family or not can_manage_settings(request.user, family):
            raise PermissionDenied("Nur Erwachsene/Owner können Regeln verwalten.")
        template = next((x for x in RULE_TEMPLATES if x["id"] == request.data.get("template_id")), None)
        if not template:
            return Response({"detail": "Unbekannte Regelvorlage."}, status=status.HTTP_400_BAD_REQUEST)
        rule = AutomationRule.objects.create(family=family, created_by=request.user, name=template["name"], icon=template["icon"], trigger_type=template["trigger_type"], trigger_config=template["trigger_config"], action_type=template["action_type"], action_config=template["action_config"])
        return Response(self.get_serializer(rule).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def run(self, request, pk=None):
        rule = self.get_object()
        if not can_manage_settings(request.user, rule.family):
            raise PermissionDenied()
        return Response({"executed": run_rule(rule)})

    @action(detail=True, methods=["post"])
    def toggle(self, request, pk=None):
        rule = self.get_object()
        if not can_manage_settings(request.user, rule.family):
            raise PermissionDenied()
        rule.enabled = not rule.enabled
        rule.save(update_fields=["enabled", "updated_at"])
        return Response(self.get_serializer(rule).data)


class FamilyEventViewSet(FamilyScopedViewSet):
    queryset = FamilyEvent.objects.all().order_by("starts_at")
    serializer_class = FamilyEventSerializer


class InboxItemViewSet(FamilyScopedViewSet):
    queryset = InboxItem.objects.all().order_by("-created_at")
    serializer_class = InboxItemSerializer

    @action(detail=True, methods=["post"])
    def to_task(self, request, pk=None):
        item = self.get_object()
        task_list, _ = TaskList.objects.get_or_create(family=item.family, name="Allgemein", defaults={"icon": "list-check"})
        task = Task.objects.create(family=item.family, task_list=task_list, title=request.data.get("title") or item.title, notes=request.data.get("notes") or item.body, created_by=request.user, source=f"inbox:{item.source}")
        item.status = "processed"
        item.save(update_fields=["status", "updated_at"])
        return Response(TaskSerializer(task).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def to_shopping(self, request, pk=None):
        item = self.get_object()
        shopping_list = ShoppingList.objects.filter(family=item.family, archived=False).order_by("sort_order", "created_at").first() or ShoppingList.objects.create(family=item.family, name="Einkauf")
        shopping_item = ShoppingItem.objects.create(shopping_list=shopping_list, name=request.data.get("name") or item.title, added_by=request.user)
        item.status = "processed"
        item.save(update_fields=["status", "updated_at"])
        return Response(ShoppingItemSerializer(shopping_item).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def dismiss(self, request, pk=None):
        item = self.get_object()
        item.status = "dismissed"
        item.save(update_fields=["status", "updated_at"])
        return Response(self.get_serializer(item).data)


@api_view(["GET"])
@permission_classes([permissions.AllowAny])
def health(request):
    return Response({"status": "ok", "service": "fam-uh-le"})


@api_view(["GET"])
def dashboard(request):
    families = list(Family.objects.filter(memberships__user=request.user).values_list("id", flat=True))
    now = timezone.now()
    tasks = Task.objects.exclude(hidden_from_user=request.user).filter(family_id__in=families, completed_at__isnull=True).select_related("task_list", "assignee").order_by("due_at", "-created_at")[:12]
    events = FamilyEvent.objects.filter(family_id__in=families, starts_at__gte=now).order_by("starts_at")[:12]
    routines = Routine.objects.filter(family_id__in=families, active=True).select_related("family").prefetch_related("logs")[:8]
    shopping = ShoppingList.objects.filter(family_id__in=families, archived=False).prefetch_related("items").order_by("sort_order", "created_at")[:8]
    task_lists = TaskList.objects.filter(family_id__in=families, archived=False).prefetch_related("tasks")[:12]
    inbox_count = InboxItem.objects.filter(family_id__in=families, status="new").count()
    automation_count = AutomationRule.objects.filter(family_id__in=families, enabled=True).count()
    return Response({"tasks": TaskSerializer(tasks, many=True).data, "task_lists": TaskListSerializer(task_lists, many=True).data, "events": FamilyEventSerializer(events, many=True).data, "routines": RoutineSerializer(routines, many=True).data, "shopping_lists": ShoppingListSerializer(shopping, many=True).data, "inbox_count": inbox_count, "automation_count": automation_count})
