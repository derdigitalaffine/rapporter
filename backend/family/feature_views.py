from django.db.models import Q
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action, api_view
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from .feature_serializers import LoyaltyCardSerializer, NotificationPreferenceSerializer
from .models import Membership
from .models_features import LoyaltyCard, NotificationPreference


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

    def get_queryset(self):
        memberships = Membership.objects.filter(user=self.request.user)
        membership_ids = memberships.values_list("id", flat=True)
        family_ids = memberships.values_list("family_id", flat=True)
        owner_family_ids = memberships.filter(role=Membership.Role.OWNER).values_list("family_id", flat=True)
        queryset = LoyaltyCard.objects.filter(family_id__in=family_ids).filter(
            Q(created_by=self.request.user)
            | Q(shared_with__id__in=membership_ids)
            | Q(family_id__in=owner_family_ids)
        ).select_related("family", "created_by", "holder_membership", "holder_membership__user").prefetch_related("shared_with", "shared_with__user").distinct()
        family_id = self.request.query_params.get("family")
        if family_id:
            queryset = queryset.filter(family_id=family_id)
        if self.request.query_params.get("include_archived") != "1":
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
            raise PermissionDenied("Nur Ersteller oder Familien-Owner können diese Karte ändern.")
        serializer.save()

    def perform_destroy(self, instance):
        if not self._can_edit(instance):
            raise PermissionDenied("Nur Ersteller oder Familien-Owner können diese Karte archivieren.")
        instance.archived = True
        instance.save(update_fields=["archived", "updated_at"])

    @action(detail=False, methods=["get"])
    def sync(self, request):
        cards = self.get_queryset().filter(archived=False)
        return Response(self.get_serializer(cards, many=True).data)
