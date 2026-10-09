from django.db.models import Q
from django.utils import timezone
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response

from .domain_notifications import notify_domain_event
from .models import InboxItem, InboxReceipt, Membership, ShoppingItem, ShoppingList, Task, TaskList
from .serializers import InboxItemSerializer, ShoppingItemSerializer, TaskSerializer


WRITER_ROLES = {Membership.Role.OWNER, Membership.Role.ADULT, Membership.Role.TEEN}


class FamilyMessageViewSet(viewsets.ModelViewSet):
    serializer_class = InboxItemSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        family_ids = Membership.objects.filter(user=self.request.user).values_list("family_id", flat=True)
        owner_family_ids = Membership.objects.filter(user=self.request.user, role=Membership.Role.OWNER).values_list("family_id", flat=True)
        visible = (
            ~Q(source="manual_message")
            | Q(audience=InboxItem.Audience.FAMILY)
            | Q(created_by=self.request.user)
            | Q(receipts__membership__user=self.request.user)
        )
        not_withdrawn = Q(withdrawn_at__isnull=True) | Q(created_by=self.request.user) | Q(family_id__in=owner_family_ids)
        return (
            InboxItem.objects.filter(family_id__in=family_ids)
            .filter(visible)
            .filter(not_withdrawn)
            .select_related("family", "created_by")
            .prefetch_related("receipts__membership__user")
            .distinct()
            .order_by("-important", "-created_at")
        )

    def perform_create(self, serializer):
        family = serializer.validated_data["family"]
        membership = Membership.objects.filter(family=family, user=self.request.user).first()
        if not membership or membership.role not in WRITER_ROLES:
            raise PermissionDenied("Diese Familienrolle darf keine Mitteilungen senden.")

        recipient_ids = serializer.validated_data.pop("recipient_ids", [])
        audience = serializer.validated_data.get("audience", InboxItem.Audience.FAMILY)
        body = (serializer.validated_data.get("body") or "").strip()
        title = (serializer.validated_data.get("title") or "").strip()
        if not body:
            raise ValidationError({"body": "Bitte gib eine Mitteilung ein."})
        if not title:
            serializer.validated_data["title"] = body[:80]

        recipients = Membership.objects.filter(family=family).exclude(user=self.request.user)
        if audience == InboxItem.Audience.SELECTED:
            if not recipient_ids:
                raise ValidationError({"recipient_ids": "Wähle mindestens einen Empfänger aus."})
            recipients = recipients.filter(id__in=recipient_ids)
            if recipients.count() != len({str(value) for value in recipient_ids if str(value) != str(membership.id)}):
                raise ValidationError({"recipient_ids": "Mindestens ein Empfänger ist ungültig."})

        item = serializer.save(created_by=self.request.user, source="manual_message", status="new")
        recipient_rows = list(recipients.select_related("user"))
        InboxReceipt.objects.bulk_create([InboxReceipt(item=item, membership=row) for row in recipient_rows], ignore_conflicts=True)
        notify_domain_event(
            family,
            "inbox.created",
            actor=self.request.user,
            target_users=[row.user_id for row in recipient_rows],
            context={"item": item.title, "inbox_id": item.id},
        )

    def perform_update(self, serializer):
        item = self.get_object()
        membership = Membership.objects.filter(family=item.family, user=self.request.user).first()
        if item.created_by_id != self.request.user.id and (not membership or membership.role != Membership.Role.OWNER):
            raise PermissionDenied("Nur Absender oder Owner dürfen Mitteilungen ändern.")
        allowed = {"important"}
        unexpected = set(serializer.validated_data) - allowed
        if unexpected:
            raise ValidationError({"detail": "Gesendete Mitteilungen können nur noch als wichtig markiert oder zurückgezogen werden."})
        serializer.save()

    def perform_destroy(self, instance):
        self._withdraw(instance)

    def _membership(self, item):
        return Membership.objects.filter(family=item.family, user=self.request.user).first()

    def _mark_read(self, item):
        membership = self._membership(item)
        if not membership:
            raise PermissionDenied()
        receipt, _ = InboxReceipt.objects.get_or_create(item=item, membership=membership)
        if not receipt.read_at:
            receipt.read_at = timezone.now()
            receipt.save(update_fields=["read_at", "updated_at"])
        return receipt

    def _withdraw(self, item):
        membership = self._membership(item)
        if item.created_by_id != self.request.user.id and (not membership or membership.role != Membership.Role.OWNER):
            raise PermissionDenied("Nur Absender oder Owner dürfen Mitteilungen zurückziehen.")
        if not item.withdrawn_at:
            item.withdrawn_at = timezone.now()
            item.save(update_fields=["withdrawn_at", "updated_at"])
        return item

    @action(detail=True, methods=["post"])
    def read(self, request, pk=None):
        item = self.get_object()
        self._mark_read(item)
        return Response(self.get_serializer(item).data)

    @action(detail=True, methods=["post"])
    def withdraw(self, request, pk=None):
        item = self._withdraw(self.get_object())
        return Response(self.get_serializer(item).data)

    @action(detail=True, methods=["post"])
    def to_task(self, request, pk=None):
        item = self.get_object()
        task_list, _ = TaskList.objects.get_or_create(family=item.family, name="Allgemein", defaults={"icon": "list-check"})
        task = Task.objects.create(family=item.family, task_list=task_list, title=request.data.get("title") or item.title, notes=request.data.get("notes") or item.body, created_by=request.user, source=f"inbox:{item.source}")
        self._mark_read(item)
        if item.source != "manual_message":
            item.status = "processed"
            item.save(update_fields=["status", "updated_at"])
        return Response(TaskSerializer(task, context={"request": request}).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def to_shopping(self, request, pk=None):
        item = self.get_object()
        shopping_list = ShoppingList.objects.filter(family=item.family, archived=False).order_by("sort_order", "created_at").first() or ShoppingList.objects.create(family=item.family, name="Einkauf")
        shopping_item = ShoppingItem.objects.create(shopping_list=shopping_list, name=request.data.get("name") or item.title, added_by=request.user)
        self._mark_read(item)
        if item.source != "manual_message":
            item.status = "processed"
            item.save(update_fields=["status", "updated_at"])
        return Response(ShoppingItemSerializer(shopping_item, context={"request": request}).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def dismiss(self, request, pk=None):
        item = self.get_object()
        self._mark_read(item)
        if item.source != "manual_message":
            item.status = "dismissed"
            item.save(update_fields=["status", "updated_at"])
        return Response(self.get_serializer(item).data)
