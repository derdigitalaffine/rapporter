import logging
from copy import deepcopy
from datetime import timedelta

from django.db import transaction
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import Membership, ShoppingItem, ShoppingList
from .serializers import ShoppingItemSerializer
from .shopping_access import visible_shopping_lists
from .shopping_models import ShoppingSession, ShoppingStore
from .shopping_session_service import start_or_join_shopping_session, touch_shopping_session_participant


logger = logging.getLogger(__name__)
PRESENCE_WINDOW = timedelta(seconds=60)


def _visible_list(user, list_id):
    if not list_id:
        return None
    return visible_shopping_lists(
        user,
        ShoppingList.objects.select_related("family").filter(id=list_id, archived=False),
    ).first()


def _visible_session_queryset(user):
    return (
        ShoppingSession.objects.filter(shopping_list__in=visible_shopping_lists(user))
        .select_related("shopping_list", "family", "started_by", "completed_by")
        .prefetch_related("participants__user")
    )


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
    if session.completed_by:
        users.append(session.completed_by)
    memberships = _membership_map(session, users)
    return {
        "id": str(session.id),
        "shopping_list": str(session.shopping_list_id),
        "status": session.status,
        "revision": session.activity_seq,
        "started_at": session.started_at,
        "completed_at": session.completed_at,
        "last_activity_at": session.last_activity_at,
        "started_by": _person(session.started_by, memberships.get(session.started_by_id), request_user),
        "completed_by": _person(session.completed_by, memberships.get(session.completed_by_id), request_user),
        "participants": [
            {
                **_person(row.user, memberships.get(row.user_id), request_user),
                "joined_at": row.joined_at,
                "last_seen_at": row.last_seen_at,
            }
            for row in participants
        ],
    }


def _active_peer_participants(session, request_user):
    cutoff = timezone.now() - PRESENCE_WINDOW
    return list(
        session.participants.filter(last_seen_at__gte=cutoff)
        .exclude(user=request_user)
        .select_related("user")
        .order_by("joined_at")
    )


def _item_snapshot(item):
    return {
        "id": str(item.id),
        "name": item.name,
        "quantity": item.quantity,
        "category": item.category,
        "aisle": item.aisle,
        "note": item.note,
        "checked_at": item.checked_at.isoformat() if item.checked_at else None,
        # The source item is deleted after checkout, so retain just enough ACL
        # metadata to keep gift/surprise items private when history is read later.
        "hidden_from_user_id": item.hidden_from_user_id,
    }


def _store_snapshot(store):
    if not store:
        return None
    return {
        "id": str(store.id),
        "name": store.name,
        "branch_label": store.branch_label,
        "address": store.address,
        "display_label": store.display_label,
    }


def _snapshot_for_user(snapshot, request_user):
    result = deepcopy(snapshot or {})
    for key, count_key in (("purchased_items", "purchased_count"), ("open_items", "open_count")):
        visible = []
        for raw in result.get(key) or []:
            row = dict(raw)
            hidden_ids = {str(value) for value in row.pop("hidden_from_user_ids", [])}
            hidden_id = row.pop("hidden_from_user_id", None)
            if hidden_id is not None:
                hidden_ids.add(str(hidden_id))
            if str(request_user.id) in hidden_ids:
                continue
            visible.append(row)
        result[key] = visible
        result[count_key] = len(visible)
    return result


def _completion_payload(session, request_user):
    return {
        "session": _session_payload(session, request_user),
        "completion": _snapshot_for_user(session.snapshot, request_user),
        "context_ref": {"type": "shopping_session", "id": str(session.id)},
    }


def _completed_cleanup_item_ids(snapshot):
    snapshot = snapshot or {}
    item_ids = [row.get("id") for row in snapshot.get("purchased_items") or [] if row.get("id")]
    if snapshot.get("open_items_policy") == "remove":
        item_ids.extend(row.get("id") for row in snapshot.get("open_items") or [] if row.get("id"))
    return item_ids


def _cleanup_completed_session_items(session):
    item_ids = _completed_cleanup_item_ids(session.snapshot)
    if not item_ids:
        return
    ShoppingItem.objects.filter(
        shopping_list_id=session.shopping_list_id,
        id__in=item_ids,
    ).delete()


def _try_cleanup_completed_session_items(session):
    try:
        # Cleanup is deliberately a second transaction. The completed session and
        # its immutable snapshot are the checkout truth and must not be rolled back
        # because a delete hook or transient database error rejects source cleanup.
        with transaction.atomic():
            _cleanup_completed_session_items(session)
        return True
    except Exception:
        logger.exception(
            "Shopping checkout item cleanup failed",
            extra={
                "shopping_session_id": str(session.id),
                "shopping_list_id": str(session.shopping_list_id),
            },
        )
        return False


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
        ShoppingSession.objects.select_related("shopping_list", "family", "started_by", "completed_by")
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
        .select_related("shopping_list", "family", "started_by", "completed_by")
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


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def shopping_session_detail(request, session_id):
    session = _visible_session_queryset(request.user).filter(id=session_id).first()
    if not session:
        return Response({"detail": "Einkaufssession nicht gefunden."}, status=status.HTTP_404_NOT_FOUND)
    return Response(_completion_payload(session, request.user))


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def shopping_session_history(request):
    shopping_list = _visible_list(request.user, request.query_params.get("shopping_list"))
    if not shopping_list:
        return Response({"detail": "Einkaufsliste nicht gefunden."}, status=status.HTTP_404_NOT_FOUND)
    try:
        limit = min(50, max(1, int(request.query_params.get("limit", "20"))))
    except (TypeError, ValueError):
        return Response({"limit": "Ungültiges Limit."}, status=status.HTTP_400_BAD_REQUEST)
    sessions = list(
        _visible_session_queryset(request.user)
        .filter(shopping_list=shopping_list, status=ShoppingSession.Status.COMPLETED)
        .order_by("-completed_at", "-updated_at")[:limit]
    )
    return Response({"results": [_completion_payload(session, request.user) for session in sessions]})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def shopping_session_complete(request):
    shopping_list = _visible_list(request.user, request.data.get("shopping_list"))
    if not shopping_list:
        return Response({"detail": "Einkaufsliste nicht gefunden."}, status=status.HTTP_404_NOT_FOUND)

    session_id = request.data.get("session")
    scope = str(request.data.get("scope") or "group").strip().lower()
    if scope not in {"group", "me"}:
        return Response({"code": "invalid_completion_scope", "detail": "Ungültige Abschlussart."}, status=status.HTTP_400_BAD_REQUEST)
    open_items_policy = str(request.data.get("open_items") or "").strip().lower()
    store_id = request.data.get("store")
    expected_revision = request.data.get("expected_revision")
    confirm_active_peers = request.data.get("confirm_active_peers") is True
    confirmed_peer_ids_raw = request.data.get("confirmed_active_peer_ids")
    if confirmed_peer_ids_raw is None:
        confirmed_peer_ids = set()
    elif isinstance(confirmed_peer_ids_raw, list):
        confirmed_peer_ids = {str(value) for value in confirmed_peer_ids_raw}
    else:
        return Response(
            {"code": "invalid_peer_confirmation", "detail": "Ungültige Bestätigung aktiver Personen."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    with transaction.atomic():
        sessions = (
            ShoppingSession.objects.select_for_update(of=("self",))
            .filter(shopping_list=shopping_list)
            .select_related("shopping_list", "family", "started_by", "completed_by")
        )
        if session_id:
            sessions = sessions.filter(id=session_id)
        else:
            sessions = sessions.filter(status=ShoppingSession.Status.ACTIVE)
        session = sessions.first()
        if not session:
            return Response({"detail": "Einkaufssession nicht gefunden."}, status=status.HTTP_404_NOT_FOUND)

        if scope == "me":
            if session.status == ShoppingSession.Status.ACTIVE:
                session.participants.filter(user=request.user).delete()
                return Response({"left": True, "session": _session_payload(session, request.user)})
            if session.status == ShoppingSession.Status.COMPLETED:
                return Response({"left": True, "session": _session_payload(session, request.user)})
            return Response({"detail": "Einkaufssession ist nicht mehr aktiv."}, status=status.HTTP_409_CONFLICT)

        if session.status != ShoppingSession.Status.COMPLETED:
            if session.status != ShoppingSession.Status.ACTIVE:
                return Response({"detail": "Einkaufssession ist nicht mehr aktiv."}, status=status.HTTP_409_CONFLICT)

            if expected_revision is not None:
                try:
                    expected_revision = int(expected_revision)
                    if expected_revision < 0:
                        raise ValueError
                except (TypeError, ValueError):
                    return Response(
                        {"code": "invalid_revision", "detail": "Ungültiger Einkaufsstand."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                if expected_revision != session.activity_seq:
                    return Response(
                        {
                            "code": "stale_session",
                            "detail": "Der Einkauf wurde inzwischen geändert. Bitte Abschluss erneut prüfen.",
                            "revision": session.activity_seq,
                            "session": _session_payload(session, request.user),
                        },
                        status=status.HTTP_409_CONFLICT,
                    )

            active_peers = _active_peer_participants(session, request.user)
            active_peer_ids = {str(row.user_id) for row in active_peers}
            if active_peers and (
                not confirm_active_peers or confirmed_peer_ids != active_peer_ids
            ):
                memberships = _membership_map(session, [row.user for row in active_peers])
                return Response(
                    {
                        "code": "active_peers_confirmation_required",
                        "detail": "Andere Personen kaufen noch ein. Gruppenabschluss bitte ausdrücklich bestätigen.",
                        "revision": session.activity_seq,
                        "participants": [
                            _person(row.user, memberships.get(row.user_id), request.user)
                            for row in active_peers
                        ],
                    },
                    status=status.HTTP_409_CONFLICT,
                )

            store = None
            if store_id:
                store = ShoppingStore.objects.filter(
                    id=store_id,
                    family_id=shopping_list.family_id,
                    active=True,
                ).first()
                if not store:
                    return Response(
                        {"code": "invalid_store", "detail": "Filiale ist für diese Einkaufsliste nicht verfügbar."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

            visible_items = list(
                ShoppingItem.objects.select_for_update()
                .filter(shopping_list=shopping_list)
                .exclude(hidden_from_user=request.user)
                .order_by("position", "created_at", "id")
            )
            purchased = [item for item in visible_items if item.checked]
            open_items = [item for item in visible_items if not item.checked]
            if not purchased:
                return Response({"code": "nothing_purchased", "detail": "Noch keine Artikel im Wagen."}, status=status.HTTP_400_BAD_REQUEST)
            if open_items and open_items_policy not in {"keep", "remove"}:
                return Response(
                    {"code": "open_items_choice_required", "open_count": len(open_items)},
                    status=status.HTTP_409_CONFLICT,
                )
            if not open_items:
                open_items_policy = "keep"

            completed_at = timezone.now()
            confirmed_store = _store_snapshot(store)
            session.status = ShoppingSession.Status.COMPLETED
            session.completed_at = completed_at
            session.completed_by = request.user
            session.last_activity_at = completed_at
            session.snapshot = {
                "version": 1,
                "shopping_list": {
                    "id": str(shopping_list.id),
                    "name": shopping_list.name,
                    "store": confirmed_store["display_label"] if confirmed_store else shopping_list.store,
                },
                "confirmed_store": confirmed_store,
                "purchased_items": [_item_snapshot(item) for item in purchased],
                "open_items": [_item_snapshot(item) for item in open_items],
                "purchased_count": len(purchased),
                "open_count": len(open_items),
                "open_items_policy": open_items_policy,
                "completed_at": completed_at.isoformat(),
                "completed_by": request.user.id,
            }
            session.save(update_fields=["status", "completed_at", "completed_by", "last_activity_at", "snapshot", "updated_at"])

    # Do mutable source cleanup only after the completed session transaction has
    # committed. Retries enter here as well, so a prior cleanup failure is repaired
    # idempotently from the immutable snapshot instead of turning checkout into 500.
    _try_cleanup_completed_session_items(session)
    return Response(_completion_payload(session, request.user))