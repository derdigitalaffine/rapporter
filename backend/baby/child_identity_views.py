from rest_framework import serializers, status
from rest_framework.decorators import api_view
from rest_framework.exceptions import NotFound
from rest_framework.response import Response

from auth_abuse.service import enforce
from auth_sessions.service import require_fresh_session
from family.models import Family

from .child_identity_service import (
    begin_child_login_activation,
    child_profile,
    guardian_settings_for_family,
    replace_child_guardians,
    require_child_guardian,
    serialize_child_identity,
)
from .models import BabyProfile
from .pregnancy_service import create_managed_child


class ManagedChildInput(serializers.Serializer):
    family = serializers.UUIDField()
    display_name = serializers.CharField(max_length=80, trim_whitespace=True)
    birth_date = serializers.DateField()
    client_identity_key = serializers.UUIDField()

    def validate_display_name(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Name must not be empty.")
        return value


class GuardianSettingsQuery(serializers.Serializer):
    family = serializers.UUIDField()


class GuardianInput(serializers.Serializer):
    membership = serializers.UUIDField()
    can_manage_account = serializers.BooleanField(default=True)


class GuardianListInput(serializers.Serializer):
    guardians = GuardianInput(many=True)


class ChildActivationInput(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(trim_whitespace=False, write_only=True)


def _child_for_visible_membership(user, membership_id):
    baby = (
        BabyProfile.objects.select_related("family", "membership__user")
        .filter(
            membership_id=membership_id,
            family__status="active",
            family__memberships__user=user,
        )
        .first()
    )
    if not baby:
        raise NotFound("Child identity not found.")
    return baby


@api_view(["POST"])
def managed_children(request):
    serializer = ManagedChildInput(data=request.data)
    serializer.is_valid(raise_exception=True)
    family = Family.objects.filter(
        pk=serializer.validated_data["family"],
        status=Family.Status.ACTIVE,
        memberships__user=request.user,
    ).first()
    if not family:
        raise NotFound("Family not found.")
    baby = create_managed_child(
        request.user,
        family,
        display_name=serializer.validated_data["display_name"],
        birth_date=serializer.validated_data["birth_date"],
        client_identity_key=serializer.validated_data["client_identity_key"],
    )
    return Response(serialize_child_identity(baby), status=status.HTTP_201_CREATED)


@api_view(["GET"])
def child_identity_by_membership(request, membership_id):
    baby = _child_for_visible_membership(request.user, membership_id)
    require_child_guardian(request.user, baby)
    return Response(serialize_child_identity(baby))


@api_view(["GET"])
def child_identity_detail(request, baby_id):
    baby = child_profile(baby_id)
    require_child_guardian(request.user, baby)
    return Response(serialize_child_identity(baby))


@api_view(["GET"])
def child_guardian_settings(request):
    serializer = GuardianSettingsQuery(data=request.query_params)
    serializer.is_valid(raise_exception=True)
    family = Family.objects.filter(
        pk=serializer.validated_data["family"],
        status=Family.Status.ACTIVE,
        memberships__user=request.user,
    ).first()
    if not family:
        raise NotFound("Family not found.")
    return Response(guardian_settings_for_family(request.user, family))


@api_view(["PUT"])
def child_guardians(request, baby_id):
    require_fresh_session(request)
    serializer = GuardianListInput(data=request.data)
    serializer.is_valid(raise_exception=True)
    baby = replace_child_guardians(
        request.user,
        baby_id,
        serializer.validated_data["guardians"],
    )
    return Response(serialize_child_identity(baby))


@api_view(["POST"])
def child_login_activation(request, baby_id):
    require_fresh_session(request)
    serializer = ChildActivationInput(data=request.data)
    serializer.is_valid(raise_exception=True)
    baby = child_profile(baby_id)
    require_child_guardian(request.user, baby, manage=True)
    email = serializer.validated_data["email"]
    decision = enforce(
        "email_verification.resend",
        request=request,
        user=request.user,
        identifier=email,
    )
    if not decision.allowed:
        response = Response(
            {"detail": "Zu viele Anfragen. Bitte später erneut versuchen.", "code": "rate_limited", "retry_after": decision.retry_after},
            status=status.HTTP_429_TOO_MANY_REQUESTS,
        )
        response["Retry-After"] = str(decision.retry_after)
        return response
    baby, _identity = begin_child_login_activation(
        request.user,
        baby_id,
        email=email,
        password=serializer.validated_data["password"],
    )
    return Response(serialize_child_identity(baby), status=status.HTTP_202_ACCEPTED)