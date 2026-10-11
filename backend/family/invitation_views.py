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
    primary_identity,
    queue_verification,
)

from .auth_views import set_user_cookies
from .invitation_audit import record_invite_audit, record_invite_expired_once
from .invitation_serializers import SafeFamilyInvitationSerializer
from .invitation_service import (
    invitation_token_digest,
    issue_invitation,
    resolve_invitation,
    rotate_invitation,
)
from .models import FamilyInvitation, Membership
from .serializers import MembershipSerializer


RATE_LIMIT_DETAIL = "Zu viele Anfragen. Bitte später erneut versuchen."
INVITE_UNAVAILABLE_DETAIL = "Einladung nicht verfügbar."


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


def _public_decision(scope, request, token, *, user=None):
    return enforce(
        scope,
        request=request,
        user=user,
        identifier=invitation_token_digest(token),
    )


def can_invite(user, family):
    return Membership.objects.filter(
        family=family,
        user=user,
        role__in=[Membership.Role.OWNER, Membership.Role.ADULT],
    ).exists()


def _masked_email(value):
    value = str(value or "")
    if "@" not in value:
        return ""
    local, domain = value.rsplit("@", 1)
    return f"{local[:1]}•••@{domain}" if local else f"•••@{domain}"


def public_invite(invite):
    return {
        "family": str(invite.family_id),
        "family_name": invite.family.name,
        "role": invite.role,
        "display_name": invite.display_name,
        "email_hint": _masked_email(invite.email),
        "expires_at": invite.expires_at,
        "active": True,
    }


def _invite_email_key(value):
    return normalize_email(value).casefold()


def validate_invite_email(invite, email):
    if not invite.email:
        return True
    try:
        return _invite_email_key(invite.email) == _invite_email_key(email)
    except EmailIdentityError:
        return False


def verified_invite_identity_matches(invite, user):
    if not invite.email:
        return True
    identity = primary_identity(user)
    if not identity or not identity.verified_at:
        return False
    try:
        return _invite_email_key(invite.email) == _invite_email_key(identity.email_normalized)
    except EmailIdentityError:
        return False


def accept_for_user(invite, user, display_name=""):
    if not invite.is_active:
        raise ValueError(INVITE_UNAVAILABLE_DETAIL)
    if not validate_invite_email(invite, user.email):
        raise ValueError("Diese Einladung ist für eine andere E-Mail-Adresse bestimmt.")
    fallback_name = (user.email or "").split("@", 1)[0] or "Mitglied"
    membership, created = Membership.objects.get_or_create(
        family=invite.family,
        user=user,
        defaults={
            "role": invite.role,
            "display_name": display_name or invite.display_name or user.get_short_name() or fallback_name,
        },
    )
    if not created:
        membership.role = invite.role if membership.role == Membership.Role.GUEST else membership.role
        if display_name and not membership.display_name:
            membership.display_name = display_name
        membership.save(update_fields=["role", "display_name", "updated_at"])
    invite.accepted_at = timezone.now()
    invite.accepted_by = user
    invite.save(update_fields=["accepted_at", "accepted_by", "updated_at"])
    record_invite_audit("invite.accepted", invite, actor=user)
    return membership


def _unavailable(invite):
    if invite is not None:
        record_invite_expired_once(invite)
    return Response({"detail": INVITE_UNAVAILABLE_DETAIL}, status=status.HTTP_404_NOT_FOUND)


class FamilyInvitationViewSet(viewsets.ModelViewSet):
    serializer_class = SafeFamilyInvitationSerializer
    permission_classes = [permissions.IsAuthenticated]
    http_method_names = ["get", "post", "delete", "head", "options"]

    def get_queryset(self):
        family_ids = Membership.objects.filter(
            user=self.request.user,
            role__in=[Membership.Role.OWNER, Membership.Role.ADULT],
        ).values_list("family_id", flat=True)
        return (
            FamilyInvitation.objects.filter(family_id__in=family_ids)
            .select_related("family", "invited_by", "accepted_by")
            .order_by("-created_at")
        )

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        family = serializer.validated_data["family"]
        if not can_invite(request.user, family):
            raise PermissionDenied("Nur Owner/Erwachsene können einladen.")
        decision = enforce("invite.create", request=request, user=request.user, family_id=family.id)
        if not decision.allowed:
            return _rate_limited_response(decision)
        role = serializer.validated_data.get("role", Membership.Role.ADULT)
        if role == Membership.Role.OWNER:
            raise PermissionDenied("Owner-Rolle kann nicht per Einladung vergeben werden.")
        expires_at = serializer.validated_data.get("expires_at") or (timezone.now() + timedelta(days=7))
        expires_at = min(expires_at, timezone.now() + timedelta(days=30))
        invite, _token = issue_invitation(
            family=family,
            invited_by=request.user,
            role=role,
            email=serializer.validated_data.get("email", ""),
            display_name=serializer.validated_data.get("display_name", ""),
            expires_at=expires_at,
        )
        output = self.get_serializer(invite)
        return Response(output.data, status=status.HTTP_201_CREATED, headers=self.get_success_headers(output.data))

    def destroy(self, request, *args, **kwargs):
        invite = self.get_object()
        if invite.accepted_at:
            return Response({"detail": "Bereits angenommene Einladung kann nicht widerrufen werden."}, status=status.HTTP_400_BAD_REQUEST)
        invite.revoked_at = timezone.now()
        invite.save(update_fields=["revoked_at", "updated_at"])
        record_invite_audit("invite.revoked", invite, actor=request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["post"])
    def renew(self, request, pk=None):
        invite = self.get_object()
        decision = enforce(
            "invite.resend",
            request=request,
            user=request.user,
            family_id=invite.family_id,
            identifier=invite.email,
        )
        if not decision.allowed:
            return _rate_limited_response(decision)
        try:
            invite, _token = rotate_invitation(invite, actor=request.user)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(self.get_serializer(invite).data)


@api_view(["GET"])
@permission_classes([permissions.AllowAny])
def invitation_info(request, token):
    decision = _public_decision("invite.resolve", request, token)
    if not decision.allowed:
        return _rate_limited_response(decision)
    invite = resolve_invitation(token)
    if not invite or not invite.is_active:
        return _unavailable(invite)
    return Response(public_invite(invite))


@api_view(["POST"])
@permission_classes([permissions.AllowAny])
def invitation_register(request, token):
    decision = _public_decision("invite.consume", request, token)
    if not decision.allowed:
        return _rate_limited_response(decision)
    User = get_user_model()
    with transaction.atomic():
        invite = resolve_invitation(token, for_update=True)
        if not invite or not invite.is_active:
            return _unavailable(invite)
        password = request.data.get("password") or ""
        display_name = (request.data.get("display_name") or invite.display_name or "").strip()
        legacy_username = (request.data.get("username") or "").strip()
        try:
            email = normalize_email(request.data.get("email") or "")
        except EmailIdentityError:
            return Response({"detail": "Bitte eine gültige E-Mail-Adresse angeben."}, status=status.HTTP_400_BAD_REQUEST)
        if len(password) < 10:
            return Response({"detail": "Passwort mindestens 10 Zeichen."}, status=status.HTTP_400_BAD_REQUEST)
        if not validate_invite_email(invite, email):
            return Response({"detail": "Diese Einladung ist für eine andere E-Mail-Adresse bestimmt."}, status=status.HTTP_403_FORBIDDEN)
        if legacy_username:
            if len(legacy_username) < 3:
                return Response({"detail": "Benutzername mindestens 3 Zeichen."}, status=status.HTTP_400_BAD_REQUEST)
            if User.objects.filter(username__iexact=legacy_username).exists():
                return Response({"detail": "Benutzername ist bereits vergeben. Bitte anmelden."}, status=status.HTTP_409_CONFLICT)
        visible_name = display_name or email.split("@", 1)[0]
        try:
            user = User.objects.create_user(
                username=legacy_username or generate_internal_username(),
                email=email,
                password=password,
                first_name=visible_name,
            )
            identity = create_primary_identity(user, email)
        except (EmailConflictError, EmailIdentityError):
            transaction.set_rollback(True)
            return Response({"detail": "E-Mail-Adresse kann nicht verwendet werden."}, status=status.HTTP_409_CONFLICT)
        membership = accept_for_user(invite, user, visible_name)
        queue_verification(identity, locale=invite.family.locale)
        response = Response(
            {
                "authenticated": True,
                "email_verification_required": True,
                "membership": MembershipSerializer(membership).data,
                "family": {"id": str(invite.family_id), "name": invite.family.name},
            },
            status=status.HTTP_201_CREATED,
        )
        return set_user_cookies(response, user, request=request)


@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def invitation_accept(request, token):
    decision = _public_decision("invite.consume", request, token, user=request.user)
    if not decision.allowed:
        return _rate_limited_response(decision)
    with transaction.atomic():
        invite = resolve_invitation(token, for_update=True)
        if not invite or not invite.is_active:
            return _unavailable(invite)
        if not verified_invite_identity_matches(invite, request.user):
            return Response(
                {"detail": "Diese Einladung erfordert die passende verifizierte E-Mail-Adresse."},
                status=status.HTTP_403_FORBIDDEN,
            )
        try:
            membership = accept_for_user(invite, request.user, (request.data.get("display_name") or "").strip())
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_403_FORBIDDEN)
        return Response(
            {
                "membership": MembershipSerializer(membership).data,
                "family": {"id": str(invite.family_id), "name": invite.family.name},
            }
        )
