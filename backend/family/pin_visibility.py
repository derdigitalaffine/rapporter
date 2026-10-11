from collections import defaultdict

from django.db.models import Q

from .models import BoardPost, Membership
from .pin_adapters import adapter_key_for_post, get_pin_adapter, unavailable_target


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
    return pin_scope_for_membership(pin, membership)


def pin_scope_for_membership(pin, membership):
    """Pure Pin-scope predicate shared by direct and batched effective ACLs."""
    if membership.family_id != pin.family_id or pin.family.status != 'active':
        return False
    if pin.author_id == membership.user_id:
        return True
    if pin.visibility == BoardPost.Visibility.FAMILY:
        return True
    if pin.visibility == BoardPost.Visibility.SELECTED:
        return any(row.pk == membership.pk for row in pin.visible_to_memberships.all())
    return False


def resolve_pin_page_visibility(pins, user):
    """Batch previews and exact effective scopes without per-Pin source reads."""
    pins = list(pins)
    targets = {pin.pk: None if not pin.target_id else unavailable_target(pin) for pin in pins}
    scopes = {pin.pk: pin.visibility if not pin.target_id else 'none' for pin in pins}
    references = [pin for pin in pins if pin.target_id]
    if not references:
        return targets, scopes
    memberships = list(Membership.objects.filter(
        family_id__in={pin.family_id for pin in references}, family__status='active',
    ).select_related('user'))
    family_members = defaultdict(set)
    authors = {}
    for member in memberships:
        family_members[member.family_id].add(member.pk)
        authors[(member.family_id, member.user_id)] = member.pk
    grouped = defaultdict(list)
    for pin in references:
        adapter = get_pin_adapter(adapter_key_for_post(pin))
        if adapter:
            grouped[adapter.key].append(pin)
    for key, rows in grouped.items():
        previews, audiences = get_pin_adapter(key).resolve_many_with_audiences(rows, user, memberships)
        targets.update(previews)
        for pin in rows:
            if pin.pk not in previews:
                continue
            allowed = audiences.get(pin.pk, set())
            if pin.visibility == BoardPost.Visibility.FAMILY and allowed == family_members[pin.family_id]:
                scopes[pin.pk] = BoardPost.Visibility.FAMILY
            elif allowed == {authors.get((pin.family_id, pin.author_id))}:
                scopes[pin.pk] = BoardPost.Visibility.PRIVATE
            else:
                scopes[pin.pk] = BoardPost.Visibility.SELECTED
    return targets, scopes


def source_object_visible(user, pin):
    """Ask the canonical source adapter whether this user may see the target."""
    if not pin.target_id:
        return True
    adapter = get_pin_adapter(adapter_key_for_post(pin))
    if adapter is None:
        return False
    return adapter.can_view(user, pin.family_id, pin.target_id)


def source_scope_for_target(*, user, family_id, adapter_key, target_id):
    """Classify the source's current audience for safe reference-pin defaults.

    This is intentionally derived through the canonical adapter for each current
    Membership. It does not mutate source ACLs and therefore cannot widen access.
    The returned selected Memberships can be copied into the Pin scope when the
    composer has not made an explicit Pin-visibility choice.
    """
    adapter = get_pin_adapter(adapter_key)
    if adapter is None:
        return BoardPost.Visibility.PRIVATE, []

    memberships = list(
        Membership.objects.filter(family_id=family_id, family__status='active').select_related('user')
    )
    allowed = [
        membership
        for membership in memberships
        if adapter.can_view(membership.user, family_id, target_id)
    ]
    allowed_ids = {membership.id for membership in allowed}
    family_ids = {membership.id for membership in memberships}
    if allowed_ids and allowed_ids == family_ids:
        return BoardPost.Visibility.FAMILY, []

    author_membership = next((membership for membership in memberships if membership.user_id == user.id), None)
    if author_membership and allowed_ids == {author_membership.id}:
        return BoardPost.Visibility.PRIVATE, []

    selected = [membership for membership in allowed if not author_membership or membership.id != author_membership.id]
    if selected:
        return BoardPost.Visibility.SELECTED, selected
    return BoardPost.Visibility.PRIVATE, []


def can_view_pin(user, pin):
    """Canonical effective visibility: PinVisibility ∩ SourceObjectVisibility."""
    return pin_scope_allows(user, pin) and source_object_visible(user, pin)


def can_interact_with_pin(user, pin):
    """Interaction gate for comments/reactions/mentions and future pin actions."""
    return can_view_pin(user, pin)


def effective_scope_for_user(user, pin):
    """Return the current effective audience class for an allowed viewer.

    Native pins have no second authority, so their stored Pin scope is already the
    effective scope. Reference pins are classified from the Memberships that pass
    both the Pin scope and the canonical source ACL. This avoids reporting
    ``family`` merely because the Pin shell says family when the source is private
    or shared only with selected people.
    """
    if not pin_scope_allows(user, pin):
        return 'none'
    if not pin.target_id:
        return pin.visibility
    if not source_object_visible(user, pin):
        return 'none'

    allowed_ids = set(visible_pin_memberships(pin).values_list('id', flat=True))
    if not allowed_ids:
        return 'none'

    family_ids = set(
        Membership.objects.filter(family_id=pin.family_id).values_list('id', flat=True)
    )
    if pin.visibility == BoardPost.Visibility.FAMILY and allowed_ids == family_ids:
        return BoardPost.Visibility.FAMILY

    author_membership_id = Membership.objects.filter(
        family_id=pin.family_id,
        user_id=pin.author_id,
    ).values_list('id', flat=True).first()
    if author_membership_id and allowed_ids == {author_membership_id}:
        return BoardPost.Visibility.PRIVATE
    return BoardPost.Visibility.SELECTED


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
