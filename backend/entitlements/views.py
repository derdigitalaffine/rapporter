from uuid import UUID

from rest_framework import permissions, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from family.models import Family, Membership

from .services import resolve_entitlements


@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def entitlement_snapshot(request):
    family_value = request.query_params.get("family")
    try:
        family_id = UUID(str(family_value))
    except (TypeError, ValueError, AttributeError):
        return Response({"detail": "Query-Parameter 'family' ist erforderlich und muss eine UUID sein."}, status=status.HTTP_400_BAD_REQUEST)

    family = Family.objects.filter(id=family_id, memberships__user=request.user).distinct().first()
    if family is None or not Membership.objects.filter(family=family, user=request.user).exists():
        # Do not reveal whether another tenant exists.
        return Response({"detail": "Familie ist für diesen Benutzer nicht verfügbar."}, status=status.HTTP_403_FORBIDDEN)

    snapshot = resolve_entitlements(family)
    return Response({"family": str(family.id), **snapshot.as_dict()})
