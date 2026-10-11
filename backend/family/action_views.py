from uuid import UUID

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from rest_framework import permissions, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response

from .action_projection import ActionProjectionError, RANKING_VERSION, parse_action_id, project_actions
from .models import Family, Membership
from .todo_models import TodoActionPreference, TodoPreference
from .todo_ranking import FOCUS_RANKING_VERSION, apply_todo_preferences, preference_payload


def _uuid_param(request, name, *, required=False):
    value = request.query_params.get(name)
    if not value:
        if required:
            raise ActionProjectionError(f"Query-Parameter '{name}' fehlt.")
        return None
    try:
        return UUID(str(value))
    except (TypeError, ValueError, AttributeError) as exc:
        raise ActionProjectionError(f"Query-Parameter '{name}' ist ungültig.") from exc


def _family_membership(request):
    try:
        family_id = _uuid_param(request, "family", required=True)
    except ActionProjectionError as exc:
        return None, None, Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
    try:
        membership = (
            Membership.objects.select_related("family")
            .filter(
                family_id=family_id,
                family__status=Family.Status.ACTIVE,
                user=request.user,
            )
            .first()
        )
    except (ValueError, DjangoValidationError):
        membership = None
    if membership is None:
        return None, None, Response(
            {"detail": "Familie ist für diesen Benutzer nicht verfügbar."},
            status=status.HTTP_403_FORBIDDEN,
        )
    return membership.family, membership, None


def _visible_action_ids(*, request, family):
    return {
        row["id"]
        for row in project_actions(user=request.user, family=family, scope="all", kind="all")
    }


def _update_preferences(request, *, family, membership):
    data = request.data if isinstance(request.data, dict) else {}
    allowed = {
        "smart_ranking_enabled",
        "today_sort",
        "action_id",
        "pinned",
        "hidden_from_focus",
        "reset",
    }
    if not data or set(data) - allowed:
        return Response({"detail": "Ungültige To-do-Präferenz."}, status=status.HTTP_400_BAD_REQUEST)
    if "reset" in data and type(data["reset"]) is not bool:
        return Response({"detail": "reset muss boolesch sein."}, status=status.HTTP_400_BAD_REQUEST)
    if "smart_ranking_enabled" in data and type(data["smart_ranking_enabled"]) is not bool:
        return Response({"detail": "smart_ranking_enabled muss boolesch sein."}, status=status.HTTP_400_BAD_REQUEST)
    if "today_sort" in data and data["today_sort"] not in TodoPreference.TodaySort.values:
        return Response({"detail": "Unbekannte Sortierung."}, status=status.HTTP_400_BAD_REQUEST)
    if "pinned" in data and type(data["pinned"]) is not bool:
        return Response({"detail": "pinned muss boolesch sein."}, status=status.HTTP_400_BAD_REQUEST)
    if "hidden_from_focus" in data and type(data["hidden_from_focus"]) is not bool:
        return Response({"detail": "hidden_from_focus muss boolesch sein."}, status=status.HTTP_400_BAD_REQUEST)

    action_id = data.get("action_id")
    if ("pinned" in data or "hidden_from_focus" in data) and not action_id:
        return Response({"detail": "action_id fehlt."}, status=status.HTTP_400_BAD_REQUEST)
    if action_id:
        try:
            _, object_id = parse_action_id(action_id)
            UUID(object_id)
        except (ActionProjectionError, ValueError, AttributeError, TypeError):
            return Response({"detail": "Ungültige Action-ID."}, status=status.HTTP_400_BAD_REQUEST)
        if action_id not in _visible_action_ids(request=request, family=family):
            return Response({"detail": "Action ist nicht verfügbar."}, status=status.HTTP_404_NOT_FOUND)

    with transaction.atomic():
        locked = Membership.objects.select_for_update().get(pk=membership.pk)
        setting, _ = TodoPreference.objects.get_or_create(membership=locked)
        if data.get("reset"):
            setting.smart_ranking_enabled = True
            setting.today_sort = TodoPreference.TodaySort.SMART
            setting.save(update_fields=["smart_ranking_enabled", "today_sort", "updated_at"])
            TodoActionPreference.objects.filter(membership=locked).delete()
            return Response(preference_payload(locked))

        changed = []
        if "smart_ranking_enabled" in data:
            setting.smart_ranking_enabled = data["smart_ranking_enabled"]
            changed.append("smart_ranking_enabled")
        if "today_sort" in data:
            setting.today_sort = data["today_sort"]
            changed.append("today_sort")
        if changed:
            setting.save(update_fields=[*changed, "updated_at"])

        if action_id:
            row, _ = TodoActionPreference.objects.get_or_create(membership=locked, action_id=action_id)
            if "pinned" in data:
                row.pinned = data["pinned"]
            if "hidden_from_focus" in data:
                row.hidden_from_focus = data["hidden_from_focus"]
            if not row.pinned and not row.hidden_from_focus:
                row.delete()
            else:
                row.save()
        return Response(preference_payload(locked))


@api_view(["GET", "PATCH"])
@permission_classes([permissions.IsAuthenticated])
def action_list(request):
    """Authorized task/routine projection plus optional explainable To-do focus."""
    family, membership, error_response = _family_membership(request)
    if error_response is not None:
        return error_response
    if request.method == "PATCH":
        return _update_preferences(request, family=family, membership=membership)

    try:
        list_id = _uuid_param(request, "list")
        workflow_id = _uuid_param(request, "workflow")
        rows = project_actions(
            user=request.user,
            family=family,
            scope=request.query_params.get("scope", "today"),
            kind=request.query_params.get("kind", "all"),
            list_id=list_id,
            workflow_id=workflow_id,
        )
    except (ActionProjectionError, ValueError, DjangoValidationError) as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    decorated, focus, preferences = apply_todo_preferences(rows, membership=membership)
    scope = request.query_params.get("scope", "today")
    if scope != "today":
        focus = []

    paginator = PageNumberPagination()
    page = paginator.paginate_queryset(decorated, request)
    response = paginator.get_paginated_response(page)
    response.data["actions"] = response.data["results"]
    response.data["focus"] = focus
    response.data["preferences"] = preferences
    response.data["ranking_version"] = RANKING_VERSION
    response.data["focus_ranking_version"] = FOCUS_RANKING_VERSION
    response.data["scope"] = scope
    return response
