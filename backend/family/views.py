from django.db.models import Q
from django.utils import timezone
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.response import Response
from .models import Family, Membership, Task, ShoppingList, ShoppingItem, Routine, RoutineLog, IntegrationSource, FamilyEvent, InboxItem
from .serializers import FamilySerializer, TaskSerializer, ShoppingListSerializer, ShoppingItemSerializer, RoutineSerializer, RoutineLogSerializer, IntegrationSourceSerializer, FamilyEventSerializer, InboxItemSerializer


def family_ids(user):
    return Membership.objects.filter(user=user).values_list("family_id", flat=True)


class FamilyScopedViewSet(viewsets.ModelViewSet):
    family_lookup = "family_id"
    def get_queryset(self):
        return self.queryset.filter(**{f"{self.family_lookup}__in": family_ids(self.request.user)})


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
            raise permissions.PermissionDenied()
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
            raise permissions.PermissionDenied()
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
    queryset = IntegrationSource.objects.all()
    serializer_class = IntegrationSourceSerializer


class FamilyEventViewSet(FamilyScopedViewSet):
    queryset = FamilyEvent.objects.all().order_by("starts_at")
    serializer_class = FamilyEventSerializer


class InboxItemViewSet(FamilyScopedViewSet):
    queryset = InboxItem.objects.all().order_by("-created_at")
    serializer_class = InboxItemSerializer


@api_view(["GET"])
@permission_classes([permissions.AllowAny])
def health(request):
    return Response({"status": "ok", "service": "fam-uh-le"})


@api_view(["GET"])
def dashboard(request):
    families = list(Family.objects.filter(memberships__user=request.user).values_list("id", flat=True))
    now = timezone.now()
    tasks = Task.objects.filter(family_id__in=families, completed_at__isnull=True).filter(Q(due_at__isnull=True) | Q(due_at__gte=now)).order_by("due_at", "-created_at")[:8]
    events = FamilyEvent.objects.filter(family_id__in=families, starts_at__gte=now).order_by("starts_at")[:8]
    routines = Routine.objects.filter(family_id__in=families, active=True).prefetch_related("logs")[:8]
    shopping = ShoppingList.objects.filter(family_id__in=families, archived=False).prefetch_related("items")[:4]
    return Response({
        "tasks": TaskSerializer(tasks, many=True).data,
        "events": FamilyEventSerializer(events, many=True).data,
        "routines": RoutineSerializer(routines, many=True).data,
        "shopping_lists": ShoppingListSerializer(shopping, many=True).data,
    })
