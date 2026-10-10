from django.db.models import Q

from family.models import Family, Membership

from .models import Document


def active_membership(user, family_id):
    if not user or not user.is_authenticated:
        return None
    return Membership.objects.filter(
        user=user,
        family_id=family_id,
        family__status=Family.Status.ACTIVE,
    ).first()


def can_view_document(user, document):
    membership = active_membership(user, document.family_id)
    if not membership:
        return False
    if document.owner_membership_id == membership.id:
        return True
    if document.visibility == Document.Visibility.FAMILY:
        return True
    if document.visibility == Document.Visibility.PRIVATE:
        return False
    return document.access_entries.filter(
        membership=membership,
    ).filter(Q(can_view=True) | Q(can_manage=True)).exists()


def can_manage_document(user, document):
    membership = active_membership(user, document.family_id)
    if not membership:
        return False
    if document.owner_membership_id == membership.id:
        return True
    if document.visibility == Document.Visibility.PRIVATE:
        return False
    return document.access_entries.filter(membership=membership, can_manage=True).exists()


def visible_documents(user, family_id, include_archived=False):
    membership = active_membership(user, family_id)
    if not membership:
        return Document.objects.none()
    query = Q(owner_membership=membership) | Q(visibility=Document.Visibility.FAMILY)
    query |= Q(
        visibility=Document.Visibility.SELECTED,
        access_entries__membership=membership,
        access_entries__can_view=True,
    )
    query |= Q(
        visibility=Document.Visibility.SELECTED,
        access_entries__membership=membership,
        access_entries__can_manage=True,
    )
    queryset = Document.objects.filter(family_id=family_id).filter(query).distinct()
    if not include_archived:
        queryset = queryset.filter(archived_at__isnull=True)
    return queryset
