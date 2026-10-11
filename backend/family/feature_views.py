from datetime import timedelta

from django.db.models import Q
from django.utils import timezone
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action, api_view
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from .feature_serializers import LoyaltyCardSerializer, NotificationPreferenceSerializer
from .models import Membership
from .models_features import LoyaltyCard, NotificationPreference
from .pass_catalog import pass_icon_catalog


def _membership(request):
    family_id = request.query_params.get("family") or request.data.get("family")
    if not family_id:
        return None
    return Membership.objects.filter(family_id=family_id, user=request.user).select_related("family").first()


@api_view(["GET", "PATCH"])
def notification_preferences(request):
    membership = _membership(request)
    if not membership:
        return Response({"detail": "Familie nicht gefunden."}, status=status.HTTP_404_NOT_FOUND)
    preference, _ = NotificationPreference.objects.get_or_create(membership=membership)
    if request.method == "PATCH":
        serializer = NotificationPreferenceSerializer(preference, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)
    return Response(NotificationPreferenceSerializer(preference).data)


class LoyaltyCardViewSet(viewsets.ModelViewSet):
    serializer_class = LoyaltyCardSerializer
    permission_classes = [permissions.IsAuthenticated]

    def _visible_memberships(self):
        return Membership.objects.filter(user=self.request.user)

    def _archive_ended_events(self, family_ids):
        now = timezone.now()
        LoyaltyCard.objects.filter(
            family_id__in=family_ids,
            archived=False,
            pass_type__in=[LoyaltyCard.PassType.TICKET, LoyaltyCard.PassType.BOARDING_PASS],
            event_ends_at__isnull=False,
            event_ends_at__lte=now,
        ).update(
            archived=True,
            archived_at=now,
            archive_reason=LoyaltyCard.ArchiveReason.EVENT_ENDED,
            restore_until=None,
            updated_at=now,
        )

    def get_queryset(self):
        memberships = self._visible_memberships()
        membership_ids = memberships.values_list("id", flat=True)
        family_ids = memberships.values_list("family_id", flat=True)
        owner_family_ids = memberships.filter(role=Membership.Role.OWNER).values_list("family_id", flat=True)
        self._archive_ended_events(family_ids)
        queryset = LoyaltyCard.objects.filter(family_id__in=family_ids).filter(
            Q(created_by=self.request.user)
            | Q(shared_with__id__in=membership_ids)
            | Q(family_id__in=owner_family_ids)
        ).select_related("family", "created_by", "holder_membership", "holder_membership__user").prefetch_related("shared_with", "shared_with__user").distinct()
        family_id = self.request.query_params.get("family")
        if family_id:
            queryset = queryset.filter(family_id=family_id)
        include_archived = self.request.query_params.get("include_archived") == "1" or getattr(self, "action", "") == "restore"
        if not include_archived:
            queryset = queryset.filter(archived=False)
        return queryset

    def _can_edit(self, card):
        if card.created_by_id == self.request.user.id:
            return True
        return Membership.objects.filter(
            family=card.family,
            user=self.request.user,
            role=Membership.Role.OWNER,
        ).exists()

    def perform_create(self, serializer):
        family = serializer.validated_data["family"]
        if not Membership.objects.filter(family=family, user=self.request.user).exists():
            raise PermissionDenied()
        serializer.save(created_by=self.request.user)

    def perform_update(self, serializer):
        card = self.get_object()
        if not self._can_edit(card):
            raise PermissionDenied("Nur Ersteller oder Familien-Owner können diesen Pass ändern.")
        serializer.save()

    def perform_destroy(self, instance):
        if not self._can_edit(instance):
            raise PermissionDenied("Nur Ersteller oder Familien-Owner können diesen Pass archivieren.")
        now = timezone.now()
        instance.archived = True
        instance.archived_at = now
        instance.archive_reason = LoyaltyCard.ArchiveReason.MANUAL
        instance.restore_until = None
        instance.save(update_fields=["archived", "archived_at", "archive_reason", "restore_until", "updated_at"])

    @action(detail=False, methods=["get"])
    def sync(self, request):
        cards = self.get_queryset().filter(archived=False)
        return Response(self.get_serializer(cards, many=True).data)

    @action(detail=False, methods=["get"])
    def catalog(self, request):
        return Response({
            "pass_types": [
                {"value": value, "label": label}
                for value, label in LoyaltyCard.PassType.choices
            ],
            "icons": pass_icon_catalog(),
            "color_modes": [value for value, _label in LoyaltyCard.ColorMode.choices],
            "undo_window": {"default_minutes": 10, "min_minutes": 1, "max_minutes": 1440},
        })

    @action(detail=True, methods=["post"])
    def redeem(self, request, pk=None):
        card = self.get_object()
        if card.archived:
            return Response({"detail": "Pass ist bereits archiviert."}, status=status.HTTP_409_CONFLICT)
        now = timezone.now()
        card.archived = True
        card.archived_at = now
        card.archive_reason = LoyaltyCard.ArchiveReason.USED
        card.used_at = now
        card.restore_until = now + timedelta(minutes=card.undo_window_minutes)
        card.save(update_fields=["archived", "archived_at", "archive_reason", "used_at", "restore_until", "updated_at"])
        return Response(self.get_serializer(card).data)

    @action(detail=True, methods=["post"])
    def restore(self, request, pk=None):
        card = self.get_object()
        now = timezone.now()
        if card.archive_reason != LoyaltyCard.ArchiveReason.USED or not card.restore_until or card.restore_until <= now:
            return Response({"detail": "Undo-Zeitfenster ist abgelaufen."}, status=status.HTTP_409_CONFLICT)
        card.archived = False
        card.archived_at = None
        card.archive_reason = ""
        card.used_at = None
        card.restore_until = None
        card.save(update_fields=["archived", "archived_at", "archive_reason", "used_at", "restore_until", "updated_at"])
        return Response(self.get_serializer(card).data)
