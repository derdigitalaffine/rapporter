from rest_framework import permissions, status, viewsets
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from .models import Membership
from .serializers import MembershipSerializer


class MembershipViewSet(viewsets.ModelViewSet):
    serializer_class = MembershipSerializer
    permission_classes = [permissions.IsAuthenticated]
    http_method_names = ["get", "patch", "delete", "head", "options"]

    def get_queryset(self):
        family_ids = Membership.objects.filter(user=self.request.user).values_list("family_id", flat=True)
        return Membership.objects.filter(family_id__in=family_ids).select_related("family", "user", "user__familyos_profile").order_by("created_at")

    def _actor_membership(self, target):
        return Membership.objects.filter(family=target.family, user=self.request.user).first()

    def partial_update(self, request, *args, **kwargs):
        target = self.get_object()
        actor = self._actor_membership(target)
        if not actor:
            raise PermissionDenied()

        requested_role = request.data.get("role", target.role)
        self_service = set(request.data.keys()).issubset({"display_name", "birthday_visibility"})
        if target.user_id == request.user.id and self_service:
            return super().partial_update(request, *args, **kwargs)

        if actor.role not in {Membership.Role.OWNER, Membership.Role.ADULT}:
            raise PermissionDenied("Nur Owner/Erwachsene können Mitglieder verwalten.")
        if target.role == Membership.Role.OWNER and actor.role != Membership.Role.OWNER:
            raise PermissionDenied("Nur ein Owner kann einen Owner verwalten.")
        if requested_role == Membership.Role.OWNER and actor.role != Membership.Role.OWNER:
            raise PermissionDenied("Nur ein Owner kann die Owner-Rolle vergeben.")

        if target.role == Membership.Role.OWNER and requested_role != Membership.Role.OWNER:
            owners = Membership.objects.filter(family=target.family, role=Membership.Role.OWNER).count()
            if owners <= 1:
                return Response({"detail": "Die Familie braucht mindestens einen Owner."}, status=status.HTTP_400_BAD_REQUEST)

        allowed = {"display_name", "role"}
        data = {key: value for key, value in request.data.items() if key in allowed}
        serializer = self.get_serializer(target, data=data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    def destroy(self, request, *args, **kwargs):
        target = self.get_object()
        actor = self._actor_membership(target)
        if not actor or actor.role not in {Membership.Role.OWNER, Membership.Role.ADULT}:
            raise PermissionDenied("Nur Owner/Erwachsene können Mitglieder entfernen.")
        if target.role == Membership.Role.OWNER:
            if actor.role != Membership.Role.OWNER:
                raise PermissionDenied("Nur ein Owner kann einen Owner entfernen.")
            if Membership.objects.filter(family=target.family, role=Membership.Role.OWNER).count() <= 1:
                return Response({"detail": "Der letzte Owner kann nicht entfernt werden."}, status=status.HTTP_400_BAD_REQUEST)
        if actor.role == Membership.Role.ADULT and target.role in {Membership.Role.OWNER, Membership.Role.ADULT} and target.id != actor.id:
            raise PermissionDenied("Erwachsene können keine Owner oder andere Erwachsene entfernen.")
        target.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
