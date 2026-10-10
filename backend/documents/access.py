from django.db.models import F, Q

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


def visible_documents_for_user(user, family_ids, include_archived=False):
    """Return documents visible to ``user`` across multiple families in one query.

    This is the canonical batch form of the document read ACL.  It deliberately
    keeps membership, ownership and selected-access checks in the Documents
    domain so projections such as Pinboard do not have to reproduce them.
    """
    if not user or not user.is_authenticated:
        return Document.objects.none()

    queryset = (
        Document.objects.filter(
            family_id__in=family_ids,
            family__status=Family.Status.ACTIVE,
            family__memberships__user=user,
        )
        .filter(
            Q(
                owner_membership__user=user,
                owner_membership__family_id=F("family_id"),
            )
            | Q(visibility=Document.Visibility.FAMILY)
            | Q(
                visibility=Document.Visibility.SELECTED,
                access_entries__membership__user=user,
                access_entries__membership__family_id=F("family_id"),
                access_entries__can_view=True,
            )
            | Q(
                visibility=Document.Visibility.SELECTED,
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


def visible_documents(user, family_id, include_archived=False):
    return visible_documents_for_user(
        user,
        [family_id],
        include_archived=include_archived,
    )
