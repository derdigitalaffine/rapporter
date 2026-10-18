from rest_framework import serializers, status
from rest_framework.decorators import api_view
from rest_framework.exceptions import NotFound, PermissionDenied
from django.db import transaction
from django.utils import timezone
from rest_framework.response import Response

from auth_abuse.service import enforce
from auth_sessions.service import require_fresh_session
from family.models import Family
from family.family_relationship_models import FamilyRelationship
from family.models import Membership
from telemetry.service import record_audit_event

from .child_identity_service import (
    begin_child_login_activation,
    child_profile,
    guardian_settings_for_family,
    replace_child_guardians,
    require_child_guardian,
    serialize_child_identity,
    attach_existing_child,
)
from .models import BabyProfile
from .pregnancy_service import create_managed_child


class ManagedChildInput(serializers.Serializer):
    family = serializers.UUIDField()
    display_name = serializers.CharField(max_length=80, trim_whitespace=True)
    birth_date = serializers.DateField()
    client_identity_key = serializers.UUIDField()
    custody_for_self = serializers.BooleanField(default=False)
    membership = serializers.UUIDField(required=False)

    def validate_birth_date(self, value):
        if value > timezone.localdate():
            raise serializers.ValidationError("A born child's birth date cannot be in the future.")
        return value

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
    confirm_custody = serializer.validated_data["custody_for_self"]
    actor = family.memberships.get(user=request.user)
    if confirm_custody:
        if actor.role != Membership.Role.OWNER:
            raise PermissionDenied("Only the family relationship administrator can record custody.")
        require_fresh_session(request)
    with transaction.atomic():
        child_member = None
        if serializer.validated_data.get("membership"):
            child_member = Membership.objects.select_for_update().filter(pk=serializer.validated_data["membership"],family=family,role=Membership.Role.CHILD).first()
            if not child_member:
                raise NotFound("Child membership not found.")
            if confirm_custody:
                relationship, created = FamilyRelationship.objects.get_or_create(family=family,child_membership=child_member,related_membership=actor,defaults={"kind":"parent","has_custody":True,"status":"active"})
                if created:
                    record_audit_event("family.custody.changed",actor=request.user,actor_class="user",family=family,target_type="relationship",target_id=str(relationship.id),metadata={"scope":"custody_granted"})
            baby = attach_existing_child(request.user,child_member,birth_date=serializer.validated_data["birth_date"],client_identity_key=serializer.validated_data["client_identity_key"])
        else:
            baby = create_managed_child(
                request.user, family, display_name=serializer.validated_data["display_name"],
                birth_date=serializer.validated_data["birth_date"],
                client_identity_key=serializer.validated_data["client_identity_key"],
            )
        if confirm_custody:
            relationship, created = FamilyRelationship.objects.get_or_create(
                family=family, child_membership=baby.membership, related_membership=actor,
                defaults={"kind": "parent", "has_custody": True, "status": "active"},
            )
            if created:
                record_audit_event("family.custody.changed", actor=request.user, actor_class="user", family=family,
                    target_type="relationship", target_id=str(relationship.id), metadata={"scope": "custody_granted"})
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
