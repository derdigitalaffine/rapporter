from django.http import Http404
from rest_framework import serializers
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from family.models import Membership
from . import services
from .access import WRITER_ROLES, blocked_ids, eligible, preferences, require_writer
from .serializers import conversation_payload


def _validated(data, **fields):
    class Input(serializers.Serializer):
        pass
    schema = Input(data=data)
    schema.fields.update(fields)
    schema.is_valid(raise_exception=True)
    return schema.validated_data


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def family_contacts(request):
    require_writer(request.user)
    blocked = blocked_ids(request.user)
    family_ids = Membership.objects.filter(
        user=request.user,
        role__in=WRITER_ROLES,
        family__status="active",
    ).values_list("family_id", flat=True)
    rows = Membership.objects.filter(
        family_id__in=family_ids,
        role__in=WRITER_ROLES,
        user__is_active=True,
    ).exclude(user=request.user).exclude(user_id__in=blocked).select_related("user").order_by("user_id", "created_at")
    result = []
    seen = set()
    for row in rows:
        if row.user_id in seen or not eligible(row.user):
            continue
        seen.add(row.user_id)
        result.append({
            "user": {
                "id": row.user_id,
                "display_name": row.display_name or preferences(row.user).display_name,
                "avatar_url": None,
            },
            "source": "family",
        })
        if len(result) >= 100:
            break
    return Response({"results": result})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def family_conversation(request):
    require_writer(request.user)
    data = _validated(request.data, user_id=serializers.IntegerField(min_value=1))
    try:
        member = services.family_direct_conversation(request.user, data["user_id"])
    except Http404:
        raise
    return Response(conversation_payload(member), status=201)
