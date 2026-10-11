from rest_framework import serializers, status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from auth_abuse.service import enforce
from auth_sessions.service import require_fresh_session

from .child_identity_service import (
    begin_child_login_activation,
    child_profile,
    replace_child_guardians,
    require_child_guardian,
    serialize_child_identity,
)


class GuardianInput(serializers.Serializer):
    membership = serializers.UUIDField()
    can_manage_account = serializers.BooleanField(default=True)


class GuardianListInput(serializers.Serializer):
    guardians = GuardianInput(many=True)


class ChildActivationInput(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(trim_whitespace=False, write_only=True)


@api_view(["GET"])
def child_identity_detail(request, baby_id):
    baby = child_profile(baby_id)
    require_child_guardian(request.user, baby)
    return Response(serialize_child_identity(baby))


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
