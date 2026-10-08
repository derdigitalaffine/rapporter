from django.db.models import Q
from django.utils import timezone
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from .integrations import INTEGRATION_CATALOG, sync_source
from .models import Family, Membership, Task, ShoppingList, ShoppingItem, Routine, RoutineLog, IntegrationSource, FamilyEvent, InboxItem
from .serializers import FamilySerializer, TaskSerializer, ShoppingListSerializer, ShoppingItemSerializer, RoutineSerializer, RoutineLogSerializer, IntegrationSourceSerializer, FamilyEventSerializer, InboxItemSerializer


def family_ids(user):
    return Membership.objects.filter(user=user).values_list("family_id", flat=True)


def can_manage_integrations(user, family):
    return Membership.objects.filter(family=family, user=user, role__in=[Membership.Role.OWNER, Membership.Role.ADULT]).exists()


class FamilyScopedViewSet(viewsets.ModelViewSet):
    family_lookup = "family_id"

    def get_queryset(self):
        return self.queryset.filter(**{f"{self.family_lookup}__in": family_ids(self.request.user)})

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


class TaskViewSet(FamilyScopedViewSet):
    queryset = Task.objects.all().order_by("completed_at", "due_at", "-created_at")
    serializer_class = TaskSerializer

    def perform_create(self, serializer):
        family = serializer.validated_data["family"]
        if not Membership.objects.filter(family=family, user=self.request.user).exists():
            raise PermissionDenied()
        serializer.save(created_by=self.request.user)

    @action(detail=True, methods=["post"])
    def toggle(self, request, pk=None):
        task = self.get_object()
        task.completed_at = None if task.completed_at else timezone.now()
        task.save(update_fields=["completed_at", "updated_at"])
        return Response(self.get_serializer(task).data)


class ShoppingListViewSet(FamilyScopedViewSet):
    queryset = ShoppingList.objects.prefetch_related("items").all()
    serializer_class = ShoppingListSerializer


class ShoppingItemViewSet(viewsets.ModelViewSet):
    queryset = ShoppingItem.objects.select_related("shopping_list").all()
    serializer_class = ShoppingItemSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return self.queryset.filter(shopping_list__family_id__in=family_ids(self.request.user))

    def perform_create(self, serializer):
        shopping_list = serializer.validated_data["shopping_list"]
        if shopping_list.family_id not in set(family_ids(self.request.user)):
            raise PermissionDenied()
        serializer.save(added_by=self.request.user)

    @action(detail=True, methods=["post"])
    def toggle(self, request, pk=None):
        item = self.get_object()
        item.checked = not item.checked
        item.save(update_fields=["checked", "updated_at"])
        return Response(self.get_serializer(item).data)


class RoutineViewSet(FamilyScopedViewSet):
    queryset = Routine.objects.prefetch_related("logs").all()
    serializer_class = RoutineSerializer

    @action(detail=True, methods=["post"])
    def done(self, request, pk=None):
        routine = self.get_object()
        log = RoutineLog.objects.create(routine=routine, done_at=timezone.now(), done_by=request.user, note=request.data.get("note", ""))
        return Response(RoutineLogSerializer(log).data, status=status.HTTP_201_CREATED)


class IntegrationSourceViewSet(FamilyScopedViewSet):
    queryset = IntegrationSource.objects.all().order_by("kind", "name")
    serializer_class = IntegrationSourceSerializer

    def perform_create(self, serializer):
        family = serializer.validated_data["family"]
        if not can_manage_integrations(self.request.user, family):
            raise PermissionDenied("Nur Erwachsene/Owner können Integrationen verwalten.")
        serializer.save()

    def perform_update(self, serializer):
        source = self.get_object()
        if not can_manage_integrations(self.request.user, source.family):
            raise PermissionDenied("Nur Erwachsene/Owner können Integrationen verwalten.")
        serializer.save()

    def perform_destroy(self, instance):
        if not can_manage_integrations(self.request.user, instance.family):
            raise PermissionDenied("Nur Erwachsene/Owner können Integrationen verwalten.")
        instance.delete()

    @action(detail=False, methods=["get"])
    def catalog(self, request):
        return Response(INTEGRATION_CATALOG)

    @action(detail=False, methods=["post"])
    def connect(self, request):
        family_id = request.data.get("family")
        catalog_id = request.data.get("catalog_id")
        family = Family.objects.filter(id=family_id, memberships__user=request.user).first()
        if not family or not can_manage_integrations(request.user, family):
            raise PermissionDenied("Nur Erwachsene/Owner können Integrationen verwalten.")
        item = next((x for x in INTEGRATION_CATALOG if x["id"] == catalog_id), None)
        if not item:
            return Response({"detail": "Unbekannte Integration."}, status=status.HTTP_400_BAD_REQUEST)
        values = dict(request.data.get("values") or {})
        endpoint = values.pop("endpoint", "")
        config = {**item.get("defaults", {}), **values}
        source = IntegrationSource.objects.create(family=family, kind=item["kind"], name=item["name"], endpoint=endpoint, config=config, enabled=True)
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
        total = 0
        errors = []
        for source in self.get_queryset().filter(enabled=True):
            try:
                total += sync_source(source)
            except Exception as exc:
                errors.append({"id": str(source.id), "name": source.name, "detail": str(exc)})
        return Response({"synced": total, "errors": errors})


class FamilyEventViewSet(FamilyScopedViewSet):
    queryset = FamilyEvent.objects.all().order_by("starts_at")
    serializer_class = FamilyEventSerializer


class InboxItemViewSet(FamilyScopedViewSet):
    queryset = InboxItem.objects.all().order_by("-created_at")
    serializer_class = InboxItemSerializer

    @action(detail=True, methods=["post"])
    def to_task(self, request, pk=None):
        item = self.get_object()
        task = Task.objects.create(family=item.family, title=request.data.get("title") or item.title, notes=request.data.get("notes") or item.body, created_by=request.user, source=f"inbox:{item.source}")
        item.status = "processed"
        item.save(update_fields=["status", "updated_at"])
        return Response(TaskSerializer(task).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def to_shopping(self, request, pk=None):
        item = self.get_object()
        shopping_list = ShoppingList.objects.filter(family=item.family, archived=False).order_by("created_at").first()
        if not shopping_list:
            shopping_list = ShoppingList.objects.create(family=item.family, name="Einkauf")
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
    tasks = Task.objects.filter(family_id__in=families, completed_at__isnull=True).filter(Q(due_at__isnull=True) | Q(due_at__gte=now)).order_by("due_at", "-created_at")[:8]
    events = FamilyEvent.objects.filter(family_id__in=families, starts_at__gte=now).order_by("starts_at")[:12]
    routines = Routine.objects.filter(family_id__in=families, active=True).prefetch_related("logs")[:8]
    shopping = ShoppingList.objects.filter(family_id__in=families, archived=False).prefetch_related("items")[:4]
    inbox_count = InboxItem.objects.filter(family_id__in=families, status="new").count()
    return Response({"tasks": TaskSerializer(tasks, many=True).data, "events": FamilyEventSerializer(events, many=True).data, "routines": RoutineSerializer(routines, many=True).data, "shopping_lists": ShoppingListSerializer(shopping, many=True).data, "inbox_count": inbox_count})
