from uuid import UUID

from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import permissions, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response

from .action_projection import ActionProjectionError, RANKING_VERSION, project_actions
from .models import Family, Membership


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


@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def action_list(request):
    """Return one authorized read projection across canonical tasks and routines."""
    try:
        family_id = _uuid_param(request, "family", required=True)
        list_id = _uuid_param(request, "list")
        workflow_id = _uuid_param(request, "workflow")
    except ActionProjectionError as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    try:
        family = Family.objects.filter(
            id=family_id,
            status=Family.Status.ACTIVE,
            memberships__user=request.user,
        ).distinct().first()
    except (ValueError, DjangoValidationError):
        family = None
    if family is None:
        # Do not reveal whether an inaccessible tenant exists.
        return Response({"detail": "Familie ist für diesen Benutzer nicht verfügbar."}, status=status.HTTP_403_FORBIDDEN)

    # Keep the membership decision server-side even for globally privileged users.
    if not Membership.objects.filter(family=family, user=request.user).exists():
        return Response({"detail": "Familie ist für diesen Benutzer nicht verfügbar."}, status=status.HTTP_403_FORBIDDEN)

    try:
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

    paginator = PageNumberPagination()
    page = paginator.paginate_queryset(rows, request)
    response = paginator.get_paginated_response(page)
    response.data["ranking_version"] = RANKING_VERSION
    response.data["scope"] = request.query_params.get("scope", "today")
    return response
