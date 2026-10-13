from decimal import Decimal, InvalidOperation
from urllib.parse import urlsplit, urlunsplit

from django.core.validators import URLValidator
from django.db import transaction
from django.core.exceptions import ValidationError as DjangoValidationError

from expenses.models import Expense
from family.context_links import create_context_link
from family.models import Membership, ShoppingItem, ShoppingList, Task

from .access import can_coordinate_item
from .models import Wishlist, WishlistAccess, WishlistItem, WishlistReservation


class ReservationConflict(Exception):
    pass


class ProjectionConflict(Exception):
    pass


def normalize_https_url(value):
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        URLValidator(schemes=["https"])(text)
    except DjangoValidationError:
        raise ValueError("invalid_https_url") from None
    parts = urlsplit(text)
    if parts.scheme.lower() != "https" or not parts.hostname or parts.username or parts.password:
        raise ValueError("invalid_https_url")
    try:
        host = parts.hostname.encode("idna").decode("ascii").lower()
        port = parts.port
    except (UnicodeError, ValueError):
        raise ValueError("invalid_https_url") from None
    if port:
        host = f"{host}:{port}"
    return urlunsplit(("https", host, parts.path or "", parts.query, ""))


def prepare_access(family_id, value):
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError("invalid_access")
    rows = []
    seen = set()
    for raw in value:
        membership_id = raw.get("membership") if isinstance(raw, dict) else raw
        membership = Membership.objects.filter(id=membership_id, family_id=family_id).first()
        if not membership:
            raise ValueError("invalid_access")
        if membership.id in seen:
            continue
        seen.add(membership.id)
        rows.append(membership)
    return rows


def replace_access(wishlist, memberships):
    wishlist.access_entries.all().delete()
    WishlistAccess.objects.bulk_create(
        [
            WishlistAccess(wishlist=wishlist, membership=membership)
            for membership in memberships
            if membership.id != wishlist.owner_membership_id
        ]
    )


def apply_item_fields(item, data):
    updates = []
    if "title" in data:
        title = str(data.get("title") or "").strip()
        if not title:
            raise ValueError("title_required")
        item.title = title[:180]
        updates.append("title")
    if "url" in data:
        item.url = normalize_https_url(data.get("url"))
        updates.append("url")
    if "note" in data:
        item.note = str(data.get("note") or "")[:4000]
        updates.append("note")
    if "priority" in data:
        priority = str(data.get("priority") or "")
        if priority and priority not in {choice for choice, _ in WishlistItem.Priority.choices}:
            raise ValueError("invalid_priority")
        item.priority = priority
        updates.append("priority")
    return updates


@transaction.atomic
def set_reservation(*, user, item_id, status, note=""):
    item = (
        WishlistItem.objects.select_for_update()
        .select_related("wishlist", "wishlist__owner_membership")
        .filter(id=item_id, archived_at__isnull=True)
        .first()
    )
    if not item or not can_coordinate_item(user, item):
        raise PermissionError("wishlist_item_unavailable")
    actor = Membership.objects.get(user=user, family=item.wishlist.family)
    if status not in {choice for choice, _ in WishlistReservation.Status.choices}:
        raise ValueError("invalid_reservation_status")
    reservation = WishlistReservation.objects.select_for_update().filter(item=item).first()
    if reservation and reservation.reserved_by_id != actor.id:
        raise ReservationConflict("already_reserved")
    if not reservation:
        reservation = WishlistReservation(item=item, reserved_by=actor)
    reservation.status = status
    reservation.note = str(note or "")[:240]
    reservation.save()
    return item, reservation


@transaction.atomic
def clear_reservation(*, user, item_id):
    item = (
        WishlistItem.objects.select_for_update()
        .select_related("wishlist", "wishlist__owner_membership")
        .filter(id=item_id, archived_at__isnull=True)
        .first()
    )
    if not item or not can_coordinate_item(user, item):
        raise PermissionError("wishlist_item_unavailable")
    actor = Membership.objects.get(user=user, family=item.wishlist.family)
    reservation = WishlistReservation.objects.select_for_update().filter(item=item).first()
    if not reservation or reservation.reserved_by_id != actor.id:
        raise PermissionError("wishlist_reservation_unavailable")
    reservation.delete()
    return item


def _action_membership(user, item):
    if not can_coordinate_item(user, item):
        raise PermissionError("wishlist_item_unavailable")
    if item.wishlist.visibility != Wishlist.Visibility.FAMILY:
        raise ProjectionConflict("selected_wishlist_action")
    return Membership.objects.get(user=user, family=item.wishlist.family)


def _link_action(user, item, target_type, target_id):
    create_context_link(
        user=user,
        family=item.wishlist.family,
        source_type="wishlist_item",
        source_id=item.id,
        context_type=target_type,
        context_id=target_id,
        relation_key="wishlist.action",
    )


def _positive_amount(value):
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError("invalid_amount") from None
    if amount <= 0:
        raise ValueError("invalid_amount")
    return amount


@transaction.atomic
def create_follow_up(*, user, item, action, payload):
    actor = _action_membership(user, item)
    title = str(payload.get("title") or item.title).strip()
    if not title:
        raise ValueError("title_required")

    if action == "task":
        created = Task.objects.create(
            family=item.wishlist.family,
            title=title[:180],
            notes=(str(payload.get("notes") or item.note or ""))[:4000],
            created_by=user,
            assignee=user,
            source=f"wishlist:{item.id}",
            hidden_from_user=item.wishlist.owner_membership.user,
        )
        _link_action(user, item, "task", created.id)
        return "task", created

    if action == "shopping":
        shopping_list = ShoppingList.objects.filter(
            id=payload.get("shopping_list"),
            family=item.wishlist.family,
            archived=False,
        ).first()
        if not shopping_list:
            raise ValueError("shopping_list_required")
        created = ShoppingItem.objects.create(
            shopping_list=shopping_list,
            name=title[:160],
            note=(str(payload.get("note") or item.note or ""))[:240],
            added_by=user,
            hidden_from_user=item.wishlist.owner_membership.user,
        )
        _link_action(user, item, "shopping_item", created.id)
        return "shopping_item", created

    if action == "expense":
        from entitlements.services import require_capability
        require_capability(user, item.wishlist.family, "expenses")
        if payload.get("acknowledge_family_visibility") is not True:
            raise ProjectionConflict("expense_family_visibility")
        amount = _positive_amount(payload.get("amount"))
        currency = str(payload.get("currency") or "EUR").strip().upper()
        if len(currency) != 3 or not currency.isalpha():
            raise ValueError("invalid_currency")
        created = Expense.objects.create(
            family=item.wishlist.family,
            title=title[:180],
            total_amount=amount,
            currency=currency,
            paid_by=actor,
            created_by=user,
            notes=(str(payload.get("note") or "Aus Wunschliste"))[:4000],
            source=Expense.Source.MANUAL,
            status=Expense.Status.POSTED,
        )
        _link_action(user, item, "expense", created.id)
        return "expense", created

    raise ValueError("unknown_action")
