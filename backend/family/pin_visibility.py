from django.db.models import Q

from .models import BoardPost, Membership
from .pin_adapters import adapter_key_for_post, get_pin_adapter


def pin_scope_queryset(user, queryset=None):
    """Return pin shells the user may see, without widening source-object access.

    Reference previews are still resolved by the canonical source adapter. Keeping
    shell visibility separate preserves the neutral unavailable lifecycle from
    #219 while interaction permission uses the effective intersection below.
    """
    rows = queryset if queryset is not None else BoardPost.objects.all()
    return rows.filter(
        family__status='active',
        family__memberships__user=user,
    ).filter(
        Q(author=user)
        | Q(visibility=BoardPost.Visibility.FAMILY)
        | Q(visibility=BoardPost.Visibility.SELECTED, visible_to_memberships__user=user)
    ).distinct()


def pin_scope_allows(user, pin):
    if not getattr(user, 'is_authenticated', False):
        return False
    membership = Membership.objects.filter(family_id=pin.family_id, user=user, family__status='active').first()
    if membership is None:
        return False
    if pin.author_id == user.id:
        return True
    if pin.visibility == BoardPost.Visibility.FAMILY:
        return True
    if pin.visibility == BoardPost.Visibility.SELECTED:
        return pin.visible_to_memberships.filter(pk=membership.pk).exists()
    return False


def source_object_visible(user, pin):
    """Ask the canonical source adapter whether this user may see the target."""
    if not pin.target_id:
        return True
    adapter = get_pin_adapter(adapter_key_for_post(pin))
    if adapter is None:
        return False
    return adapter.can_view(user, pin.family_id, pin.target_id)


def can_view_pin(user, pin):
    """Canonical effective visibility: PinVisibility ∩ SourceObjectVisibility."""
    return pin_scope_allows(user, pin) and source_object_visible(user, pin)


def can_interact_with_pin(user, pin):
    """Interaction gate for comments/reactions/mentions and future pin actions."""
    return can_view_pin(user, pin)


def effective_scope_for_user(user, pin):
    if not pin_scope_allows(user, pin) or not source_object_visible(user, pin):
        return 'none'
    return pin.visibility


def visible_pin_memberships(pin):
    """Resolve memberships with effective access for notification/activity consumers.

    The candidate set is bounded by one family. Source ACL checks remain delegated
    to the registered adapter, so future consumers cannot accidentally widen a
    document, note, gift, school, care, or other domain policy.
    """
    if pin.family.status != 'active':
        return Membership.objects.none()

    memberships = Membership.objects.filter(family_id=pin.family_id).select_related('user')
    if pin.visibility == BoardPost.Visibility.PRIVATE:
        memberships = memberships.filter(user_id=pin.author_id)
    elif pin.visibility == BoardPost.Visibility.SELECTED:
        memberships = memberships.filter(
            Q(user_id=pin.author_id) | Q(visible_board_posts=pin)
        ).distinct()

    if not pin.target_id:
        return memberships

    adapter = get_pin_adapter(adapter_key_for_post(pin))
    if adapter is None:
        return Membership.objects.none()
    allowed_ids = [
        membership.id
        for membership in memberships
        if adapter.can_view(membership.user, pin.family_id, pin.target_id)
    ]
    return Membership.objects.filter(pk__in=allowed_ids)
