from datetime import timedelta

from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import Membership, ShoppingItem, ShoppingList
from .serializers import ShoppingItemSerializer
from .shopping_access import visible_shopping_lists
from .shopping_models import ShoppingSession
from .shopping_session_service import start_or_join_shopping_session, touch_shopping_session_participant


PRESENCE_WINDOW = timedelta(seconds=60)


def _visible_list(user, list_id):
    if not list_id:
        return None
    return visible_shopping_lists(
        user,
        ShoppingList.objects.select_related("family").filter(id=list_id, archived=False),
    ).first()


def _membership_map(session, users):
    user_ids = {user.id for user in users if user}
    return {
        row.user_id: row
        for row in Membership.objects.filter(family=session.family, user_id__in=user_ids).select_related("user")
    }


def _person(user, membership, request_user):
    if not user:
        return None
    name = (
        (membership.display_name if membership else "")
        or user.get_short_name()
        or user.username
    )
    return {
        "id": user.id,
        "name": name,
        "avatar": membership.avatar if membership else "",
        "is_self": user.id == request_user.id,
    }


def _session_payload(session, request_user):
    cutoff = timezone.now() - PRESENCE_WINDOW
    participants = list(
        session.participants.filter(last_seen_at__gte=cutoff)
        .select_related("user")
        .order_by("joined_at")
    )
    users = [row.user for row in participants]
    if session.started_by:
        users.append(session.started_by)
    memberships = _membership_map(session, users)
    return {
        "id": str(session.id),
        "shopping_list": str(session.shopping_list_id),
        "status": session.status,
        "started_at": session.started_at,
        "last_activity_at": session.last_activity_at,
        "started_by": _person(session.started_by, memberships.get(session.started_by_id), request_user),
        "participants": [
            {
                **_person(row.user, memberships.get(row.user_id), request_user),
                "joined_at": row.joined_at,
                "last_seen_at": row.last_seen_at,
            }
            for row in participants
        ],
    }


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def shopping_session_start(request):
    shopping_list = _visible_list(request.user, request.data.get("shopping_list"))
    if not shopping_list:
        return Response({"detail": "Einkaufsliste nicht gefunden."}, status=status.HTTP_404_NOT_FOUND)
    session, created = start_or_join_shopping_session(shopping_list, request.user)
    if not session:
        return Response({"detail": "Einkaufsliste nicht gefunden."}, status=status.HTTP_404_NOT_FOUND)
    session = (
        ShoppingSession.objects.select_related("shopping_list", "family", "started_by")
        .prefetch_related("participants__user")
        .get(pk=session.pk)
    )
    return Response({
        "session": _session_payload(session, request.user),
        "cursor": session.activity_seq,
        "activities": [],
        "created": created,
    }, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def shopping_session_current(request):
    shopping_list = _visible_list(request.user, request.query_params.get("shopping_list"))
    if not shopping_list:
        return Response({"detail": "Einkaufsliste nicht gefunden."}, status=status.HTTP_404_NOT_FOUND)
    session = (
        ShoppingSession.objects.filter(
            shopping_list=shopping_list,
            status=ShoppingSession.Status.ACTIVE,
        )
        .select_related("shopping_list", "family", "started_by")
        .prefetch_related("participants__user")
        .first()
    )
    if not session:
        return Response({"session": None, "cursor": 0, "activities": []})
    touch_shopping_session_participant(session, request.user)
    try:
        after = max(0, int(request.query_params.get("after", "0")))
    except (TypeError, ValueError):
        return Response({"after": "Ungültiger Activity-Cursor."}, status=status.HTTP_400_BAD_REQUEST)

    activities = list(
        session.activities.filter(sequence__gt=after)
        .select_related("actor")
        .order_by("sequence")[:100]
    )
    item_ids = [row.item_id for row in activities if row.item_id]
    items = {
        str(item.id): item
        for item in ShoppingItem.objects.filter(shopping_list=shopping_list, id__in=item_ids)
        .exclude(hidden_from_user=request.user)
    }
    actor_users = [row.actor for row in activities if row.actor]
    memberships = _membership_map(session, actor_users)
    serialized = []
    for row in activities:
        item = items.get(str(row.item_id)) if row.item_id else None
        # Item-level privacy is re-evaluated at read time. If a previously visible
        # item is now hidden (or was deleted), do not leak its stored snapshot name
        # or actor through the append-only activity stream.
        if row.item_id and not item:
            continue
        serialized.append({
            "sequence": row.sequence,
            "kind": row.kind,
            "item_id": str(row.item_id) if row.item_id else None,
            "item_name": row.item_name,
            "actor": _person(row.actor, memberships.get(row.actor_id), request.user),
            "item": ShoppingItemSerializer(item, context={"request": request}).data if item else None,
            "created_at": row.created_at,
        })
    # Advance over filtered rows as well, otherwise a client could refetch the same
    # hidden activity forever and turn filtering into an existence side channel.
    cursor = activities[-1].sequence if activities else session.activity_seq
    return Response({
        "session": _session_payload(session, request.user),
        "cursor": cursor,
        "activities": serialized,
    })