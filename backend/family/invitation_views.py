from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from auth_abuse.service import enforce
from auth_identity.service import (
    EmailConflictError,
    EmailIdentityError,
    create_primary_identity,
    generate_internal_username,
    normalize_email,
    queue_verification,
)

from .auth_views import set_user_cookies
from .models import Family, FamilyInvitation, Membership
from .serializers import FamilyInvitationSerializer, MembershipSerializer


RATE_LIMIT_DETAIL = "Zu viele Anfragen. Bitte später erneut versuchen."


def _rate_limited_response(decision):
    response = Response(
        {
            "detail": RATE_LIMIT_DETAIL,
            "code": "rate_limited",
            "retry_after": decision.retry_after,
        },
        status=status.HTTP_429_TOO_MANY_REQUESTS,
    )
    response["Retry-After"] = str(decision.retry_after)
    return response


def can_invite(user, family):
    return Membership.objects.filter(
        family=family,
        user=user,
        role__in=[Membership.Role.OWNER, Membership.Role.ADULT],
    ).exists()


def public_invite(invite):
    return {
        "family": str(invite.family_id),
        "family_name": invite.family.name,
        "role": invite.role,
        "display_name": invite.display_name,
        "email_hint": invite.email if invite.email else "",
        "expires_at": invite.expires_at,
        "active": invite.is_active,
    }


def validate_invite_email(invite, email):
    if not invite.email:
        return True
    try:
        return normalize_email(invite.email) == normalize_email(email)
    except EmailIdentityError:
        return False


def accept_for_user(invite, user, display_name=""):
    if not invite.is_active:
        raise ValueError("Diese Einladung ist abgelaufen, widerrufen oder bereits verwendet.")
    if not validate_invite_email(invite, user.email):
        raise ValueError("Diese Einladung ist für eine andere E-Mail-Adresse bestimmt.")
    fallback_name = (user.email or "").split("@", 1)[0] or "Mitglied"
    membership, created = Membership.objects.get_or_create(
        family=invite.family,
        user=user,
        defaults={"role": invite.role, "display_name": display_name or invite.display_name or user.get_short_name() or fallback_name},
    )
    if not created:
        membership.role = invite.role if membership.role == Membership.Role.GUEST else membership.role
        if display_name and not membership.display_name:
            membership.display_name = display_name
        membership.save(update_fields=["role", "display_name", "updated_at"])
    invite.accepted_at = timezone.now()
    invite.accepted_by = user
    invite.save(update_fields=["accepted_at", "accepted_by", "updated_at"])
    return membership


class FamilyInvitationViewSet(viewsets.ModelViewSet):
    serializer_class = FamilyInvitationSerializer
    permission_classes = [permissions.IsAuthenticated]
    http_method_names = ["get", "post", "delete", "head", "options"]

    def get_queryset(self):
        family_ids = Membership.objects.filter(
            user=self.request.user,
            role__in=[Membership.Role.OWNER, Membership.Role.ADULT],
        ).values_list("family_id", flat=True)
        return FamilyInvitation.objects.filter(family_id__in=family_ids).select_related("family", "invited_by", "accepted_by").order_by("-created_at")

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        family = serializer.validated_data["family"]
        if not can_invite(request.user, family):
            raise PermissionDenied("Nur Owner/Erwachsene können einladen.")

        decision = enforce(
            "invite.create",
            request=request,
            user=request.user,
            family_id=family.id,
        )
        if not decision.allowed:
            return _rate_limited_response(decision)

        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    def perform_create(self, serializer):
        family = serializer.validated_data["family"]
        if not can_invite(self.request.user, family):
            raise PermissionDenied("Nur Owner/Erwachsene können einladen.")
        role = serializer.validated_data.get("role", Membership.Role.ADULT)
        if role == Membership.Role.OWNER:
            raise PermissionDenied("Owner-Rolle kann nicht per Einladung vergeben werden.")
        expires_at = serializer.validated_data.get("expires_at")
        if not expires_at:
            expires_at = timezone.now() + timedelta(days=7)
        max_expiry = timezone.now() + timedelta(days=30)
        if expires_at > max_expiry:
            expires_at = max_expiry
        serializer.save(invited_by=self.request.user, expires_at=expires_at)

    def destroy(self, request, *args, **kwargs):
        invite = self.get_object()
        if invite.accepted_at:
            return Response({"detail": "Bereits angenommene Einladung kann nicht widerrufen werden."}, status=status.HTTP_400_BAD_REQUEST)
        invite.revoked_at = timezone.now()
        invite.save(update_fields=["revoked_at", "updated_at"])
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["post"])
    def renew(self, request, pk=None):
        invite = self.get_object()
        decision = enforce(
            "invite.resend",
            request=request,
            user=request.user,
            family_id=invite.family_id,
        )
        if not decision.allowed:
            return _rate_limited_response(decision)
        if invite.accepted_at:
            return Response({"detail": "Bereits angenommen."}, status=status.HTTP_400_BAD_REQUEST)
        invite.revoked_at = None
        invite.expires_at = timezone.now() + timedelta(days=7)
        invite.save(update_fields=["revoked_at", "expires_at", "updated_at"])
        return Response(self.get_serializer(invite).data)


@api_view(["GET"])
@permission_classes([permissions.AllowAny])
def invitation_info(request, token):
    invite = FamilyInvitation.objects.select_related("family").filter(token=token).first()
    if not invite:
        return Response({"detail": "Einladung nicht gefunden."}, status=status.HTTP_404_NOT_FOUND)
    return Response(public_invite(invite))


@api_view(["POST"])
@permission_classes([permissions.AllowAny])
def invitation_register(request, token):
    User = get_user_model()
    with transaction.atomic():
        invite = FamilyInvitation.objects.select_for_update().select_related("family").filter(token=token).first()
        if not invite or not invite.is_active:
            return Response({"detail": "Diese Einladung ist nicht mehr gültig."}, status=status.HTTP_400_BAD_REQUEST)
        password = request.data.get("password") or ""
        display_name = (request.data.get("display_name") or invite.display_name or "").strip()
        try:
            email = normalize_email(request.data.get("email") or "")
        except EmailIdentityError:
            return Response({"detail": "Bitte eine gültige E-Mail-Adresse angeben."}, status=status.HTTP_400_BAD_REQUEST)
        if len(password) < 10:
            return Response({"detail": "Passwort mindestens 10 Zeichen."}, status=status.HTTP_400_BAD_REQUEST)
        if not validate_invite_email(invite, email):
            return Response({"detail": "Diese Einladung ist für eine andere E-Mail-Adresse bestimmt."}, status=status.HTTP_403_FORBIDDEN)
        visible_name = display_name or email.split("@", 1)[0]
        try:
            user = User.objects.create_user(
                username=generate_internal_username(),
                email=email,
                password=password,
                first_name=visible_name,
            )
            identity = create_primary_identity(user, email)
        except (EmailConflictError, EmailIdentityError):
            return Response({"detail": "E-Mail-Adresse kann nicht verwendet werden."}, status=status.HTTP_409_CONFLICT)
        membership = accept_for_user(invite, user, visible_name)
        queue_verification(identity, locale=invite.family.locale)
        response = Response({
            "authenticated": True,
            "email_verification_required": True,
            "membership": MembershipSerializer(membership).data,
            "family": {"id": str(invite.family_id), "name": invite.family.name},
        }, status=status.HTTP_201_CREATED)
        return set_user_cookies(response, user)


@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def invitation_accept(request, token):
    with transaction.atomic():
        invite = FamilyInvitation.objects.select_for_update().select_related("family").filter(token=token).first()
        if not invite or not invite.is_active:
            return Response({"detail": "Diese Einladung ist nicht mehr gültig."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            membership = accept_for_user(invite, request.user, (request.data.get("display_name") or "").strip())
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_403_FORBIDDEN)
        return Response({"membership": MembershipSerializer(membership).data, "family": {"id": str(invite.family_id), "name": invite.family.name}})
