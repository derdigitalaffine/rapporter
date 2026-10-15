from django.http import Http404
from rest_framework import permissions, serializers, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from auth_sessions.service import require_fresh_session
from telemetry.service import try_record_audit_event

from .family_relationship_models import FamilyRelationship
from .models import Family, Membership


CUSTODY_ROLES = {Membership.Role.OWNER, Membership.Role.ADULT}


class FamilyRelationshipInputSerializer(serializers.Serializer):
    family = serializers.UUIDField(required=False)
    child_membership = serializers.UUIDField(required=False)
    related_membership = serializers.UUIDField(required=False)
    kind = serializers.ChoiceField(
        choices=FamilyRelationship.Kind.choices,
        required=False,
    )
    custom_label = serializers.CharField(
        max_length=80,
        allow_blank=True,
        required=False,
        trim_whitespace=True,
    )
    is_biological_parent = serializers.BooleanField(required=False)
    is_legal_parent = serializers.BooleanField(required=False)
    has_custody = serializers.BooleanField(required=False, allow_null=True)
    status = serializers.ChoiceField(
        choices=FamilyRelationship.Status.choices,
        required=False,
    )
    child_visibility = serializers.ChoiceField(
        choices=FamilyRelationship.ChildVisibility.choices,
        required=False,
    )

    def validate(self, attrs):
        kind = attrs.get(
            "kind",
            getattr(self.instance, "kind", FamilyRelationship.Kind.PARENT),
        )
        custom_label = attrs.get(
            "custom_label",
            getattr(self.instance, "custom_label", ""),
        )
        if kind == FamilyRelationship.Kind.OTHER and not str(custom_label).strip():
            raise serializers.ValidationError(
                {"custom_label": "Bitte eine eigene Bezeichnung angeben."}
            )
        if kind == FamilyRelationship.Kind.NONE and str(custom_label).strip():
            raise serializers.ValidationError(
                {
                    "custom_label": (
                        "Ohne Bezeichnung kann keine eigene Bezeichnung gesetzt werden."
                    )
                }
            )
        return attrs


def _family_membership(user, family_id, *, hide=False):
    row = (
        Membership.objects.filter(
            user=user,
            family_id=family_id,
            family__status=Family.Status.ACTIVE,
        )
        .select_related("family")
        .first()
    )
    if row:
        return row
    if hide:
        raise Http404()
    raise PermissionDenied("Familie ist für diesen Benutzer nicht verfügbar.")


def _owner(actor):
    if actor.role != Membership.Role.OWNER:
        raise PermissionDenied("Nur Owner dürfen Familienbeziehungen ändern.")


def _member(family, membership_id, field):
    member = (
        Membership.objects.filter(pk=membership_id, family=family)
        .select_related("user")
        .first()
    )
    if not member:
        raise serializers.ValidationError(
            {field: "Mitglied gehört nicht zu dieser Familie."}
        )
    return member


def _effective_custody(*, has_custody, relationship_status, related_role):
    return bool(
        has_custody is True
        and relationship_status == FamilyRelationship.Status.ACTIVE
        and related_role in CUSTODY_ROLES
    )


def _audit_custody_change(row, user, scope):
    try_record_audit_event(
        "family.custody.changed",
        actor=user,
        actor_class="user",
        family=row.family,
        target_type="relationship",
        target_id=str(row.pk),
        metadata={"scope": scope},
    )


def _permission_suggestions(row):
    active = row.status == FamilyRelationship.Status.ACTIVE
    adult = row.related_membership.role in CUSTODY_ROLES
    custody_authority = bool(active and adult and row.has_custody is True)
    return {
        "account_management": custody_authority,
        "care_circle": bool(
            active and adult and row.kind != FamilyRelationship.Kind.NONE
        ),
        "automatic": custody_authority,
        "child_authority": custody_authority,
    }


def _relationship_payload(row, *, actor):
    child_viewer = actor.role == Membership.Role.CHILD
    visibility = row.child_visibility
    if child_viewer and visibility == FamilyRelationship.ChildVisibility.HIDDEN:
        return None
    sensitive_visible = (
        actor.role == Membership.Role.OWNER
        or (
            child_viewer
            and actor.id == row.child_membership_id
            and visibility == FamilyRelationship.ChildVisibility.FULL
        )
    )
    return {
        "id": str(row.id),
        "family": str(row.family_id),
        "child_membership": str(row.child_membership_id),
        "child_display_name": (
            row.child_membership.display_name
            or row.child_membership.user.username
        ),
        "related_membership": str(row.related_membership_id),
        "related_display_name": (
            row.related_membership.display_name
            or row.related_membership.user.username
        ),
        "related_role": row.related_membership.role,
        "kind": row.kind,
        "label": row.display_label,
        "custom_label": row.custom_label,
        "is_biological_parent": (
            row.is_biological_parent if sensitive_visible else None
        ),
        "is_legal_parent": row.is_legal_parent if sensitive_visible else None,
        "has_custody": row.has_custody if sensitive_visible else None,
        "status": row.status,
        "child_visibility": row.child_visibility,
        "can_edit": actor.role == Membership.Role.OWNER,
        "permission_suggestions": (
            _permission_suggestions(row) if sensitive_visible else None
        ),
    }


@api_view(["GET", "POST"])
@permission_classes([permissions.IsAuthenticated])
def family_relationships(request):
    family_id = (
        request.query_params.get("family")
        if request.method == "GET"
        else request.data.get("family")
    )
    if not family_id:
        raise serializers.ValidationError({"family": "Familie fehlt."})
    actor = _family_membership(request.user, family_id)

    if request.method == "GET":
        rows = FamilyRelationship.objects.filter(family=actor.family).select_related(
            "child_membership__user",
            "related_membership__user",
        )
        if actor.role == Membership.Role.CHILD:
            rows = rows.filter(child_membership=actor)
        else:
            child_id = request.query_params.get("child_membership")
            if child_id:
                rows = rows.filter(child_membership_id=child_id)
        payload = []
        for row in rows.order_by("child_membership__created_at", "created_at"):
            serialized = _relationship_payload(row, actor=actor)
            if serialized is not None:
                payload.append(serialized)
        return Response(payload)

    _owner(actor)
    incoming = FamilyRelationshipInputSerializer(data=request.data)
    incoming.is_valid(raise_exception=True)
    values = incoming.validated_data
    child_id = values.get("child_membership")
    related_id = values.get("related_membership")
    if not child_id:
        raise serializers.ValidationError({"child_membership": "Kind fehlt."})
    if not related_id:
        raise serializers.ValidationError({"related_membership": "Bezugsperson fehlt."})
    child = _member(actor.family, child_id, "child_membership")
    related = _member(actor.family, related_id, "related_membership")
    if child.role != Membership.Role.CHILD:
        raise serializers.ValidationError(
            {
                "child_membership": (
                    "Familienbeziehungen können nur einem Kind zugeordnet werden."
                )
            }
        )
    if child.id == related.id:
        raise serializers.ValidationError(
            {
                "related_membership": (
                    "Eine Person kann nicht ihre eigene Familienbeziehung sein."
                )
            }
        )
    if values.get("has_custody") is True and related.role not in CUSTODY_ROLES:
        raise serializers.ValidationError(
            {"has_custody": "Sorgerecht kann nur Erwachsenen zugeordnet werden."}
        )
    if FamilyRelationship.objects.filter(
        family=actor.family,
        child_membership=child,
        related_membership=related,
    ).exists():
        raise serializers.ValidationError(
            {
                "related_membership": (
                    "Für diese Person existiert bereits eine Familienbeziehung "
                    "zu diesem Kind."
                )
            }
        )
    if values.get("has_custody") is True:
        require_fresh_session(request)
    row = FamilyRelationship(
        family=actor.family,
        child_membership=child,
        related_membership=related,
        kind=values.get("kind", FamilyRelationship.Kind.PARENT),
        custom_label=values.get("custom_label", ""),
        is_biological_parent=values.get("is_biological_parent", False),
        is_legal_parent=values.get("is_legal_parent", False),
        has_custody=values.get("has_custody", None),
        status=values.get("status", FamilyRelationship.Status.ACTIVE),
        child_visibility=values.get(
            "child_visibility",
            FamilyRelationship.ChildVisibility.RELATIONSHIP_ONLY,
        ),
    )
    row.full_clean()
    row.save()
    if row.has_custody is True:
        scope = (
            "custody_granted"
            if _effective_custody(
                has_custody=row.has_custody,
                relationship_status=row.status,
                related_role=row.related_membership.role,
            )
            else "custody_recorded_inactive"
        )
        _audit_custody_change(row, request.user, scope)
    return Response(
        _relationship_payload(row, actor=actor),
        status=status.HTTP_201_CREATED,
    )


@api_view(["PATCH"])
@permission_classes([permissions.IsAuthenticated])
def family_relationship_detail(request, relationship_id):
    row = (
        FamilyRelationship.objects.select_related(
            "family",
            "child_membership__user",
            "related_membership__user",
        )
        .filter(pk=relationship_id)
        .first()
    )
    if not row:
        raise Http404()
    actor = _family_membership(request.user, row.family_id, hide=True)
    _owner(actor)
    incoming = FamilyRelationshipInputSerializer(
        instance=row,
        data=request.data,
        partial=True,
    )
    incoming.is_valid(raise_exception=True)
    values = incoming.validated_data
    immutable = {"family", "child_membership", "related_membership"} & set(values)
    if immutable:
        raise serializers.ValidationError(
            {
                field: "Diese Zuordnung kann nicht nachträglich geändert werden."
                for field in immutable
            }
        )

    before_custody = row.has_custody
    before_effective = _effective_custody(
        has_custody=row.has_custody,
        relationship_status=row.status,
        related_role=row.related_membership.role,
    )
    next_custody = values.get("has_custody", row.has_custody)
    next_status = values.get("status", row.status)
    if next_custody is True and row.related_membership.role not in CUSTODY_ROLES:
        raise serializers.ValidationError(
            {"has_custody": "Sorgerecht kann nur Erwachsenen zugeordnet werden."}
        )
    after_effective = _effective_custody(
        has_custody=next_custody,
        relationship_status=next_status,
        related_role=row.related_membership.role,
    )
    custody_value_changed = (
        "has_custody" in values and next_custody != before_custody
    )
    authority_changed = before_effective != after_effective
    if custody_value_changed or authority_changed:
        require_fresh_session(request)

    for field in (
        "kind",
        "custom_label",
        "is_biological_parent",
        "is_legal_parent",
        "has_custody",
        "status",
        "child_visibility",
    ):
        if field in values:
            setattr(row, field, values[field])
    row.full_clean()
    row.save()

    if custody_value_changed or authority_changed:
        if not before_effective and after_effective:
            scope = "custody_granted"
        elif before_effective and not after_effective:
            scope = "custody_revoked"
        else:
            scope = "custody_record_changed"
        _audit_custody_change(row, request.user, scope)
    return Response(_relationship_payload(row, actor=actor))
