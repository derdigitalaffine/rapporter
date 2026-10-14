from uuid import UUID

from django.core.exceptions import PermissionDenied as DjangoPermissionDenied, ValidationError as DjangoValidationError
from django.db import transaction
from rest_framework import permissions, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from .action_views import _family_membership
from .models import FamilyEvent, Membership, Task
from .scheduling_dependencies import (
    create_relative_dependency,
    dependency_payload,
    materialization_payload,
    preview_relative_dependency,
    update_relative_dependency,
)
from .scheduling_detach import detach_materialization_fields
from .scheduling_models import SchedulingDependency, SchedulingMaterialization, SchedulingSeries
from .unified_action_models import Action


MANAGER_ROLES = {Membership.Role.OWNER, Membership.Role.ADULT}


def _uuid(value, field):
    try:
        return UUID(str(value))
    except (TypeError, ValueError, AttributeError) as exc:
        raise DjangoValidationError({field: "Ungültige ID."}) from exc


def _error(exc):
    if isinstance(exc, DjangoPermissionDenied):
        return Response({"detail": str(exc)}, status=status.HTTP_403_FORBIDDEN)
    detail = getattr(exc, "message_dict", None) or getattr(exc, "messages", None) or str(exc)
    return Response(detail if isinstance(detail, dict) else {"detail": detail}, status=status.HTTP_400_BAD_REQUEST)


def _dependency(family, dependency_id):
    return SchedulingDependency.objects.filter(family=family, id=dependency_id).first()


def _can_manage(dependency, user):
    if getattr(user, "is_superuser", False):
        return True
    membership = Membership.objects.filter(family=dependency.family, user=user).first()
    return bool(membership and (membership.role in MANAGER_ROLES or dependency.created_by_id == user.id))


@api_view(["GET", "POST"])
@permission_classes([permissions.IsAuthenticated])
def scheduling_dependencies(request):
    family, _membership, error_response = _family_membership(request)
    if error_response is not None:
        return error_response
    language = request.query_params.get("language") or family.locale or "de"
    if request.method == "GET":
        rows = SchedulingDependency.objects.filter(family=family).order_by("created_at")
        anchor_type = request.query_params.get("anchor_type")
        anchor_id = request.query_params.get("anchor_id")
        output_type = request.query_params.get("output_type")
        output_id = request.query_params.get("output_id")
        if anchor_type:
            rows = rows.filter(anchor_type=anchor_type)
        if anchor_id:
            try:
                rows = rows.filter(anchor_id=_uuid(anchor_id, "anchor_id"))
            except DjangoValidationError as exc:
                return _error(exc)
        result = []
        for row in rows[:100]:
            item = dependency_payload(row, language=language)
            item["materializations"] = [materialization_payload(value) for value in row.materializations.order_by("scheduled_for")[:12]]
            result.append(item)

        origins = []
        if output_id:
            try:
                output_uuid = _uuid(output_id, "output_id")
            except DjangoValidationError as exc:
                return _error(exc)
            materializations = SchedulingMaterialization.objects.filter(family=family, output_id=output_uuid).select_related("dependency").order_by("scheduled_for")
            if output_type:
                materializations = materializations.filter(output_type=output_type)
            for materialization in materializations[:12]:
                origin = materialization_payload(materialization)
                origin["dependency"] = dependency_payload(materialization.dependency, language=language)
                origins.append(origin)
        return Response({"dependencies": result, "origins": origins})

    data = request.data if isinstance(request.data, dict) else {}
    allowed = {"anchor_type", "anchor_id", "anchor_scope", "anchor_occurrence_key", "output_type", "output_blueprint", "relative_rule", "inheritance", "conflict_policy"}
    if not data or set(data) - allowed:
        return Response({"detail": "Ungültige Abhängigkeitsregel."}, status=status.HTTP_400_BAD_REQUEST)
    try:
        dependency = create_relative_dependency(
            family=family,
            anchor_type=data.get("anchor_type"),
            anchor_id=_uuid(data.get("anchor_id"), "anchor_id"),
            output_type=data.get("output_type"),
            relative_rule=data.get("relative_rule"),
            actor=request.user,
            anchor_scope=data.get("anchor_scope") or SchedulingDependency.AnchorScope.SERIES,
            anchor_occurrence_key=data.get("anchor_occurrence_key") or "",
            output_blueprint=data.get("output_blueprint") or {},
            inheritance=data.get("inheritance") or {},
            conflict_policy=data.get("conflict_policy") or {},
        )
    except (DjangoValidationError, DjangoPermissionDenied, ValueError) as exc:
        return _error(exc)
    result = dependency_payload(dependency, language=family.locale or "de")
    result["materializations"] = [materialization_payload(value) for value in dependency.materializations.order_by("scheduled_for")[:12]]
    return Response(result, status=status.HTTP_201_CREATED)


@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def scheduling_dependency_preview(request):
    family, _membership, error_response = _family_membership(request)
    if error_response is not None:
        return error_response
    data = request.data if isinstance(request.data, dict) else {}
    allowed = {"anchor_type", "anchor_id", "output_type", "output_blueprint", "relative_rule", "inheritance", "language", "limit"}
    if not data or set(data) - allowed:
        return Response({"detail": "Ungültige Abhängigkeitsvorschau."}, status=status.HTTP_400_BAD_REQUEST)
    try:
        result = preview_relative_dependency(
            family=family,
            anchor_type=data.get("anchor_type"),
            anchor_id=_uuid(data.get("anchor_id"), "anchor_id"),
            relative_rule=data.get("relative_rule"),
            output_type=data.get("output_type"),
            output_blueprint=data.get("output_blueprint") or {},
            inheritance=data.get("inheritance") or {},
            language=data.get("language") or family.locale or "de",
            limit=max(1, min(10, int(data.get("limit") or 5))),
        )
    except (DjangoValidationError, DjangoPermissionDenied, ValueError, TypeError) as exc:
        return _error(exc)
    return Response(result)


@api_view(["PATCH", "DELETE"])
@permission_classes([permissions.IsAuthenticated])
def scheduling_dependency_detail(request, dependency_id):
    family, _membership, error_response = _family_membership(request)
    if error_response is not None:
        return error_response
    dependency = _dependency(family, dependency_id)
    if dependency is None:
        return Response({"detail": "Abhängigkeitsregel nicht gefunden."}, status=status.HTTP_404_NOT_FOUND)
    if not _can_manage(dependency, request.user):
        return Response({"detail": "Keine Berechtigung für diese Abhängigkeitsregel."}, status=status.HTTP_403_FORBIDDEN)
    if request.method == "PATCH":
        try:
            dependency = update_relative_dependency(dependency, actor=request.user, changes=request.data if isinstance(request.data, dict) else {})
        except (DjangoValidationError, DjangoPermissionDenied, ValueError) as exc:
            return _error(exc)
        result = dependency_payload(dependency, language=family.locale or "de")
        result["materializations"] = [materialization_payload(value) for value in dependency.materializations.order_by("scheduled_for")[:12]]
        return Response(result)

    outputs = request.query_params.get("outputs", "keep")
    if outputs not in {"keep", "delete"}:
        return Response({"detail": "outputs muss keep oder delete sein."}, status=status.HTTP_400_BAD_REQUEST)
    with transaction.atomic():
        materializations = list(dependency.materializations.select_for_update())
        if outputs == "delete":
            for row in materializations:
                if not row.output_id or row.status == SchedulingMaterialization.Status.DETACHED:
                    continue
                if row.output_type == SchedulingDependency.OutputType.EVENT:
                    FamilyEvent.objects.filter(family=family, id=row.output_id).delete()
                elif row.output_type == SchedulingDependency.OutputType.ACTION:
                    action = Action.objects.filter(family=family, id=row.output_id).select_related("legacy_task").first()
                    if action and action.legacy_task_id:
                        Task.objects.filter(family=family, id=action.legacy_task_id).delete()
        dependency.delete()
    return Response(status=status.HTTP_204_NO_CONTENT)


@api_view(["PATCH"])
@permission_classes([permissions.IsAuthenticated])
def scheduling_materialization_detach(request, materialization_id):
    family, _membership, error_response = _family_membership(request)
    if error_response is not None:
        return error_response
    row = SchedulingMaterialization.objects.select_related("dependency").filter(family=family, id=materialization_id).first()
    if row is None:
        return Response({"detail": "Ableitung nicht gefunden."}, status=status.HTTP_404_NOT_FOUND)
    if not _can_manage(row.dependency, request.user):
        return Response({"detail": "Keine Berechtigung für diese Ableitung."}, status=status.HTTP_403_FORBIDDEN)
    data = request.data if isinstance(request.data, dict) else {}
    if set(data) - {"fields", "detached"}:
        return Response({"detail": "Ungültige Ablösung."}, status=status.HTTP_400_BAD_REQUEST)
    if data.get("detached") is True:
        row.status = SchedulingMaterialization.Status.DETACHED
        row.save(update_fields=["status", "updated_at"])
        return Response(materialization_payload(row))
    if data.get("detached") is False:
        row.status = SchedulingMaterialization.Status.MATERIALIZED
        row.save(update_fields=["status", "updated_at"])
    try:
        row = detach_materialization_fields(row, data.get("fields") or [])
    except DjangoValidationError as exc:
        return _error(exc)
    return Response(materialization_payload(row))
