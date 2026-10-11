from django.db.models import F, Q

from family.models import Family, Membership

from .models import Contract


def active_membership(user, family_id):
    if not user or not user.is_authenticated:
        return None
    return Membership.objects.filter(
        user=user,
        family_id=family_id,
        family__status=Family.Status.ACTIVE,
    ).first()


def visible_contracts(user, family_id, include_archived=False):
    if not user or not user.is_authenticated:
        return Contract.objects.none()
    queryset = (
        Contract.objects.filter(
            family_id=family_id,
            family__status=Family.Status.ACTIVE,
            family__memberships__user=user,
        )
        .filter(
            Q(owner_membership__user=user, owner_membership__family_id=F("family_id"))
            | Q(visibility=Contract.Visibility.FAMILY)
            | Q(
                visibility=Contract.Visibility.SELECTED,
                access_entries__membership__user=user,
                access_entries__membership__family_id=F("family_id"),
                access_entries__can_view=True,
            )
            | Q(
                visibility=Contract.Visibility.SELECTED,
                access_entries__membership__user=user,
                access_entries__membership__family_id=F("family_id"),
                access_entries__can_manage=True,
            )
        )
        .distinct()
    )
    if not include_archived:
        queryset = queryset.filter(archived_at__isnull=True)
    return queryset


def can_view_contract(user, contract):
    return visible_contracts(user, contract.family_id, include_archived=True).filter(pk=contract.pk).exists()


def can_manage_contract(user, contract):
    membership = active_membership(user, contract.family_id)
    if not membership:
        return False
    if contract.owner_membership_id == membership.id:
        return True
    if contract.visibility == Contract.Visibility.PRIVATE:
        return False
    return contract.access_entries.filter(membership=membership, can_manage=True).exists()
