from .access import active_membership, can_coordinate_item, can_manage_wishlist
from .models import WishlistReservation


def _membership_payload(membership):
    return {
        "id": str(membership.id),
        "name": membership.display_name or membership.user.username,
        "role": membership.role,
    }


def _reservation_payload(reservation, actor_membership):
    return {
        "status": reservation.status,
        "reserved_by": _membership_payload(reservation.reserved_by),
        "note": reservation.note,
        "mine": bool(actor_membership and reservation.reserved_by_id == actor_membership.id),
    }


def item_payload(item, user):
    actor = active_membership(user, item.wishlist.family_id)
    payload = {
        "id": str(item.id),
        "wishlist": str(item.wishlist_id),
        "title": item.title,
        "url": item.url,
        "note": item.note,
        "priority": item.priority,
        "created_at": item.created_at.isoformat(),
        "can_reserve": can_coordinate_item(user, item),
    }
    # Surprise data is intentionally absent, not merely nulled, for the list owner.
    if actor and actor.id != item.wishlist.owner_membership_id:
        try:
            reservation = item.reservation
        except WishlistReservation.DoesNotExist:
            reservation = None
        payload["reservation"] = _reservation_payload(reservation, actor) if reservation else None
    return payload


def wishlist_payload(wishlist, user):
    owner = can_manage_wishlist(user, wishlist)
    payload = {
        "id": str(wishlist.id),
        "family": str(wishlist.family_id),
        "title": wishlist.title,
        "visibility": wishlist.visibility,
        "active": wishlist.active,
        "owner": _membership_payload(wishlist.owner_membership),
        "is_owner": owner,
        "can_manage": owner,
        "items": [
            item_payload(item, user)
            for item in wishlist.items.all()
            if item.archived_at is None
        ],
    }
    if owner:
        payload["access"] = [
            _membership_payload(row.membership)
            for row in wishlist.access_entries.all()
            if row.membership_id != wishlist.owner_membership_id
        ]
    return payload
