import uuid

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .context_links import (
    ContextLinkPermissionDenied,
    ContextObjectUnavailable,
    ContextRef,
    InvalidContextReference,
    UnsupportedContextRelation,
    UnsupportedContextType,
    create_context_link,
    default_context_registry,
    list_context_links,
    remove_context_link,
)
from .models import Family


def _error_response(exc):
    if isinstance(exc, InvalidContextReference):
        return Response({"code": str(exc) or "invalid_context_reference"}, status=status.HTTP_400_BAD_REQUEST)
    if isinstance(exc, UnsupportedContextType):
        return Response({"code": "unsupported_context_type"}, status=status.HTTP_400_BAD_REQUEST)
    if isinstance(exc, UnsupportedContextRelation):
        return Response({"code": "unsupported_context_relation"}, status=status.HTTP_400_BAD_REQUEST)
    if isinstance(exc, ContextObjectUnavailable):
        return Response({"code": "context_object_unavailable"}, status=status.HTTP_404_NOT_FOUND)
    if isinstance(exc, ContextLinkPermissionDenied):
        return Response({"code": "context_link_forbidden"}, status=status.HTTP_403_FORBIDDEN)
    raise exc


def _active_family(user, raw_family_id):
    if not raw_family_id:
        raise InvalidContextReference("family_required")
    try:
        family_id = raw_family_id if isinstance(raw_family_id, uuid.UUID) else uuid.UUID(str(raw_family_id))
    except (TypeError, ValueError, AttributeError):
        raise InvalidContextReference("invalid_family_id") from None
    family = Family.objects.filter(
        id=family_id,
        status=Family.Status.ACTIVE,
        memberships__user=user,
    ).first()
    if not family:
        raise ContextObjectUnavailable("family_unavailable")
    return family


def _payload_ref(payload, key):
    value = payload.get(key)
    if not isinstance(value, dict):
        raise InvalidContextReference(f"{key}_required")
    return ContextRef.parse(value.get("type"), value.get("id"))


def _serialize_endpoint(resolved):
    return {
        "type": resolved.ref.type,
        "id": str(resolved.ref.id),
        "lifecycle": resolved.lifecycle,
        "deep_link": resolved.deep_link,
    }


def _serialize_link(link, source, context):
    return {
        "id": str(link.id),
        "relation": link.relation_key,
        "source": _serialize_endpoint(source),
        "context": _serialize_endpoint(context),
        "created_at": link.created_at,
    }


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def context_links(request):
    try:
        if request.method == "POST":
            family = _active_family(request.user, request.data.get("family"))
            source_ref = _payload_ref(request.data, "source")
            context_ref = _payload_ref(request.data, "context")
            relation_key = str(request.data.get("relation") or "context").strip()
            registry = default_context_registry()
            link, created = create_context_link(
                user=request.user,
                family=family,
                source_type=source_ref.type,
                source_id=source_ref.id,
                context_type=context_ref.type,
                context_id=context_ref.id,
                relation_key=relation_key,
                registry=registry,
            )
            # Visibility remains domain-owned even inside this request. If an ACL
            # changes between creation and response serialization, fail closed
            # instead of dereferencing a now-invisible endpoint.
            resolved = registry.resolve_many(request.user, family, [source_ref, context_ref])
            if source_ref not in resolved or context_ref not in resolved:
                raise ContextObjectUnavailable("context_object_unavailable")
            body = {
                "created": created,
                "link": _serialize_link(link, resolved[source_ref], resolved[context_ref]),
            }
            return Response(body, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)

        family = _active_family(request.user, request.query_params.get("family"))
        anchor = ContextRef.parse(
            request.query_params.get("anchor_type"),
            request.query_params.get("anchor_id"),
        )
        raw_limit = request.query_params.get("limit", "50")
        try:
            limit = int(raw_limit)
        except (TypeError, ValueError):
            raise InvalidContextReference("invalid_limit") from None
        rows = list_context_links(
            user=request.user,
            family=family,
            anchor_type=anchor.type,
            anchor_id=anchor.id,
            limit=limit,
        )
        return Response(
            {
                "count": len(rows),
                "results": [_serialize_link(row.link, row.source, row.context) for row in rows],
            }
        )
    except (
        InvalidContextReference,
        UnsupportedContextType,
        UnsupportedContextRelation,
        ContextObjectUnavailable,
        ContextLinkPermissionDenied,
    ) as exc:
        return _error_response(exc)


@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
def context_link_detail(request, link_id):
    try:
        family = _active_family(request.user, request.query_params.get("family"))
        remove_context_link(user=request.user, family=family, link_id=link_id)
        return Response(status=status.HTTP_204_NO_CONTENT)
    except (
        InvalidContextReference,
        UnsupportedContextType,
        UnsupportedContextRelation,
        ContextObjectUnavailable,
        ContextLinkPermissionDenied,
    ) as exc:
        return _error_response(exc)
