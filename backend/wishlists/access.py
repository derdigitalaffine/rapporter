from django.db.models import F, Q

from family.models import Family, Membership

from .models import Wishlist, WishlistItem


CREATOR_ROLES = {Membership.Role.OWNER, Membership.Role.ADULT}
COORDINATOR_ROLES = {Membership.Role.OWNER, Membership.Role.ADULT, Membership.Role.TEEN}


def active_membership(user, family_id):
    if not user or not user.is_authenticated:
        return None
    return Membership.objects.filter(
        user=user,
        family_id=family_id,
        family__status=Family.Status.ACTIVE,
    ).first()


def can_create_wishlist(user, family_id):
    membership = active_membership(user, family_id)
    return bool(membership and membership.role in CREATOR_ROLES)


def visible_wishlists(user, family_id, *, include_inactive=False):
    if not user or not user.is_authenticated:
        return Wishlist.objects.none()
    queryset = (
        Wishlist.objects.filter(
            family_id=family_id,
            family__status=Family.Status.ACTIVE,
            family__memberships__user=user,
        )
        .filter(
            Q(owner_membership__user=user, owner_membership__family_id=F("family_id"))
            | Q(visibility=Wishlist.Visibility.FAMILY)
            | Q(
                visibility=Wishlist.Visibility.SELECTED,
                access_entries__membership__user=user,
                access_entries__membership__family_id=F("family_id"),
            )
        )
        .distinct()
    )
    if not include_inactive:
        queryset = queryset.filter(active=True)
    return queryset


def can_view_wishlist(user, wishlist):
    return visible_wishlists(user, wishlist.family_id, include_inactive=True).filter(pk=wishlist.pk).exists()


def can_manage_wishlist(user, wishlist):
    membership = active_membership(user, wishlist.family_id)
    return bool(membership and wishlist.owner_membership_id == membership.id)


def visible_items(user, family_id, *, include_archived=False):
    queryset = WishlistItem.objects.filter(wishlist__in=visible_wishlists(user, family_id, include_inactive=True))
    if not include_archived:
        queryset = queryset.filter(archived_at__isnull=True)
    return queryset.distinct()


def can_view_item(user, item):
    return can_view_wishlist(user, item.wishlist) and item.archived_at is None


def can_coordinate_item(user, item):
    membership = active_membership(user, item.wishlist.family_id)
    if not membership or membership.role not in COORDINATOR_ROLES:
        return False
    if item.archived_at or not item.wishlist.active or not can_view_wishlist(user, item.wishlist):
        return False
    return item.wishlist.owner_membership_id != membership.id
