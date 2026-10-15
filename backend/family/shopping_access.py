from django.db import transaction
from django.db.models import Q
from django.db.models.signals import pre_save
from django.dispatch import receiver
from rest_framework.exceptions import PermissionDenied, ValidationError

from .memory import normalize_name
from .models import EntryMemory, Membership, ShoppingList, ShoppingPurchaseEvent
from .shopping_models import ShoppingListAccess


GROUP_ROLES = {
    "adults": (Membership.Role.OWNER, Membership.Role.ADULT),
    "children": (Membership.Role.TEEN, Membership.Role.CHILD),
}


@receiver(pre_save, sender=ShoppingList)
def shopping_list_family_guard(sender, instance, **kwargs):
    """Do not let an ACL-bearing list move between families.

    ShoppingListAccess points at concrete Membership rows. Moving the parent
    list would otherwise leave visibility/responsibility references attached to
    the previous family. Legacy lists without an access row keep their existing
    behavior until they opt into the explicit access contract.
    """
    if not instance.pk:
        return
    previous_family_id = ShoppingList.objects.filter(pk=instance.pk).values_list("family_id", flat=True).first()
    if (
        previous_family_id
        and previous_family_id != instance.family_id
        and ShoppingListAccess.objects.filter(shopping_list_id=instance.pk).exists()
    ):
        raise ValidationError({"family": "Einkaufslisten mit Freigaben können nicht zwischen Familien verschoben werden."})


def visible_shopping_lists(user, queryset=None):
    """Return ShoppingLists visible to ``user`` without widening family ACLs.

    Legacy lists have no ShoppingListAccess row and intentionally remain
    family-visible. This preserves the existing contract while new lists can be
    private or explicitly selected.
    """
    queryset = queryset if queryset is not None else ShoppingList.objects.all()
    family_ids = Membership.objects.filter(user=user).values_list("family_id", flat=True)
    return (
        queryset.filter(family_id__in=family_ids)
        .filter(
            Q(access_settings__isnull=True)
            | Q(access_settings__visibility=ShoppingListAccess.Visibility.FAMILY)
            | Q(access_settings__created_by=user)
            | Q(
                access_settings__visibility=ShoppingListAccess.Visibility.SELECTED,
                access_settings__visible_members__user=user,
            )
        )
        .distinct()
    )


def can_access_shopping_list(user, shopping_list):
    return visible_shopping_lists(
        user,
        ShoppingList.objects.filter(pk=shopping_list.pk),
    ).exists()


def _membership(user, family):
    return Membership.objects.filter(user=user, family=family).first()


def can_manage_shopping_access(user, shopping_list):
    membership = _membership(user, shopping_list.family)
    if not membership or membership.role == Membership.Role.GUEST:
        return False
    try:
        access = shopping_list.access_settings
    except ShoppingListAccess.DoesNotExist:
        # Legacy rows have no trustworthy creator metadata. Keep them visible
        # family-wide, but only adults/owners may convert that shared contract.
        return membership.role in {Membership.Role.OWNER, Membership.Role.ADULT}
    return access.created_by_id == user.id or membership.role in {
        Membership.Role.OWNER,
        Membership.Role.ADULT,
    }


def shopping_notification_user_ids(shopping_list):
    """Return explicit recipient user IDs, or ``None`` for a family-wide list."""
    try:
        access = shopping_list.access_settings
    except ShoppingListAccess.DoesNotExist:
        return None
    if access.visibility == ShoppingListAccess.Visibility.FAMILY:
        return None
    ids = set(access.visible_members.values_list("user_id", flat=True))
    if access.created_by_id:
        ids.add(access.created_by_id)
    return list(ids)


def _members_for_ids(family, raw_ids, *, field_name):
    raw_ids = [str(value) for value in (raw_ids or []) if value]
    if len(raw_ids) != len(set(raw_ids)):
        raw_ids = list(dict.fromkeys(raw_ids))
    members = list(Membership.objects.filter(family=family, id__in=raw_ids).select_related("user"))
    if len(members) != len(raw_ids):
        raise ValidationError({field_name: "Alle ausgewählten Personen müssen zur aktiven Familie gehören."})
    return members


def expand_audience_group(family, group_key):
    """Expand built-in family cohorts to concrete Membership rows.

    This is deliberately not a second group/identity model. A future canonical
    saved-groups core can feed the same explicit-members contract.
    """
    if not group_key:
        return []
    if group_key == "family":
        return list(Membership.objects.filter(family=family).select_related("user"))
    roles = GROUP_ROLES.get(group_key)
    if not roles:
        raise ValidationError({"audience_group": "Unbekannte Personengruppe."})
    return list(Membership.objects.filter(family=family, role__in=roles).select_related("user"))


def _merge_members(*groups):
    merged = {}
    for group in groups:
        for member in group:
            merged[str(member.id)] = member
    return list(merged.values())


def _scrub_family_learning(shopping_list):
    """Remove family-wide learning derived from a list that becomes restricted.

    Purchase events retain their source list and can be removed exactly. Entry
    memory is normalized family-wide and has no source pointer, so remove the
    affected names conservatively; public usage can learn them again later.
    """
    normalized_names = {
        normalize_name(name)
        for name in shopping_list.items.values_list("name", flat=True)
        if normalize_name(name)
    }
    ShoppingPurchaseEvent.objects.filter(shopping_list=shopping_list).delete()
    if normalized_names:
        EntryMemory.objects.filter(
            family=shopping_list.family,
            kind=EntryMemory.Kind.SHOPPING,
            normalized_name__in=normalized_names,
        ).delete()


@transaction.atomic
def set_shopping_access(
    shopping_list,
    *,
    actor,
    visibility=None,
    visible_member_ids=None,
    responsible_member_ids=None,
    audience_group=None,
    allow_initialize=False,
):
    if not _membership(actor, shopping_list.family):
        raise PermissionDenied("Einkaufsliste gehört nicht zu deiner Familie.")
    existing = ShoppingListAccess.objects.filter(shopping_list=shopping_list).first()
    if not existing and not allow_initialize and not can_manage_shopping_access(actor, shopping_list):
        raise PermissionDenied("Du kannst die Freigabe dieser Liste nicht ändern.")
    if existing and not can_manage_shopping_access(actor, shopping_list):
        raise PermissionDenied("Du kannst die Freigabe dieser Liste nicht ändern.")

    previous_mode = existing.visibility if existing else ShoppingListAccess.Visibility.FAMILY
    mode = visibility or previous_mode
    valid_modes = {choice for choice, _ in ShoppingListAccess.Visibility.choices}
    if mode not in valid_modes:
        raise ValidationError({"visibility": "Ungültige Sichtbarkeit."})

    if visible_member_ids is None and existing:
        selected = list(existing.visible_members.select_related("user").all())
    else:
        selected = _members_for_ids(
            shopping_list.family,
            visible_member_ids or [],
            field_name="visible_members",
        )
    if audience_group:
        selected = _merge_members(selected, expand_audience_group(shopping_list.family, audience_group))

    if responsible_member_ids is None and existing:
        responsible = list(existing.responsible_members.select_related("user").all())
    else:
        responsible = _members_for_ids(
            shopping_list.family,
            responsible_member_ids or [],
            field_name="responsible_members",
        )

    if mode == ShoppingListAccess.Visibility.SELECTED and not selected:
        raise ValidationError({"visible_members": "Wähle mindestens eine Person oder Gruppe aus."})

    if previous_mode == ShoppingListAccess.Visibility.FAMILY and mode != ShoppingListAccess.Visibility.FAMILY:
        _scrub_family_learning(shopping_list)

    access, _ = ShoppingListAccess.objects.select_for_update().get_or_create(
        shopping_list=shopping_list,
        defaults={"created_by": actor, "visibility": mode},
    )
    if not access.created_by_id:
        access.created_by = actor
    access.visibility = mode
    access.save(update_fields=["created_by", "visibility", "updated_at"])
    access.visible_members.set(selected if mode == ShoppingListAccess.Visibility.SELECTED else [])
    access.responsible_members.set(responsible)
    return access


def serialize_shopping_access(shopping_list, *, actor=None):
    try:
        access = shopping_list.access_settings
    except ShoppingListAccess.DoesNotExist:
        payload = {
            "visibility": ShoppingListAccess.Visibility.FAMILY,
            "visible_members": [],
            "responsible_members": [],
            "legacy_family_default": True,
        }
        if actor is not None:
            payload["can_manage"] = can_manage_shopping_access(actor, shopping_list)
        return payload

    def row(member):
        return {
            "id": str(member.id),
            "user_id": member.user_id,
            "name": member.display_name or member.user.get_short_name() or member.user.username,
            "role": member.role,
            "avatar": member.avatar,
        }

    payload = {
        "visibility": access.visibility,
        "visible_members": [row(member) for member in access.visible_members.select_related("user").all()],
        "responsible_members": [row(member) for member in access.responsible_members.select_related("user").all()],
        "legacy_family_default": False,
    }
    if actor is not None:
        payload["can_manage"] = can_manage_shopping_access(actor, shopping_list)
    return payload
