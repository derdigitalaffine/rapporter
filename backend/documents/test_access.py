from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from family.models import Family, Membership

from .access import visible_documents, visible_documents_for_user
from .models import Document, DocumentAccess


class DocumentVisibilityBatchTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.viewer = User.objects.create_user(username="batch-viewer")
        self.owner = User.objects.create_user(username="batch-owner")
        self.outsider = User.objects.create_user(username="batch-outsider")

        self.family_a = Family.objects.create(name="Batch A", slug="batch-a")
        self.family_b = Family.objects.create(name="Batch B", slug="batch-b")
        self.family_c = Family.objects.create(name="Batch C", slug="batch-c")
        self.suspended = Family.objects.create(
            name="Batch Suspended",
            slug="batch-suspended",
            status=Family.Status.SUSPENDED,
        )

        self.viewer_a = Membership.objects.create(
            family=self.family_a,
            user=self.viewer,
            role=Membership.Role.ADULT,
        )
        self.viewer_b = Membership.objects.create(
            family=self.family_b,
            user=self.viewer,
            role=Membership.Role.ADULT,
        )
        self.viewer_suspended = Membership.objects.create(
            family=self.suspended,
            user=self.viewer,
            role=Membership.Role.ADULT,
        )
        self.owner_a = Membership.objects.create(
            family=self.family_a,
            user=self.owner,
            role=Membership.Role.OWNER,
        )
        self.owner_b = Membership.objects.create(
            family=self.family_b,
            user=self.owner,
            role=Membership.Role.OWNER,
        )
        self.owner_c = Membership.objects.create(
            family=self.family_c,
            user=self.owner,
            role=Membership.Role.OWNER,
        )
        self.owner_suspended = Membership.objects.create(
            family=self.suspended,
            user=self.owner,
            role=Membership.Role.OWNER,
        )
        self.outsider_a = Membership.objects.create(
            family=self.family_a,
            user=self.outsider,
            role=Membership.Role.ADULT,
        )

    def document(self, *, family, owner_membership, visibility, title, archived=False):
        return Document.objects.create(
            family=family,
            owner_membership=owner_membership,
            visibility=visibility,
            title=title,
            canonical_file=f"documents/{title}.pdf",
            mime_type="application/pdf",
            size=1,
            sha256=(title.encode("utf-8").hex() + "0" * 64)[:64],
            archived_at=timezone.now() if archived else None,
        )

    def test_batch_visibility_preserves_owner_family_selected_and_membership_rules(self):
        owned_private = self.document(
            family=self.family_a,
            owner_membership=self.viewer_a,
            visibility=Document.Visibility.PRIVATE,
            title="owned-private",
        )
        foreign_private = self.document(
            family=self.family_a,
            owner_membership=self.owner_a,
            visibility=Document.Visibility.PRIVATE,
            title="foreign-private",
        )
        family_visible = self.document(
            family=self.family_a,
            owner_membership=self.owner_a,
            visibility=Document.Visibility.FAMILY,
            title="family-visible",
        )
        selected_view = self.document(
            family=self.family_a,
            owner_membership=self.owner_a,
            visibility=Document.Visibility.SELECTED,
            title="selected-view",
        )
        DocumentAccess.objects.create(
            document=selected_view,
            membership=self.viewer_a,
            can_view=True,
        )
        selected_manage = self.document(
            family=self.family_b,
            owner_membership=self.owner_b,
            visibility=Document.Visibility.SELECTED,
            title="selected-manage",
        )
        DocumentAccess.objects.create(
            document=selected_manage,
            membership=self.viewer_b,
            can_view=False,
            can_manage=True,
        )
        selected_other = self.document(
            family=self.family_a,
            owner_membership=self.owner_a,
            visibility=Document.Visibility.SELECTED,
            title="selected-other",
        )
        DocumentAccess.objects.create(
            document=selected_other,
            membership=self.outsider_a,
            can_view=True,
        )
        no_membership_family = self.document(
            family=self.family_c,
            owner_membership=self.owner_c,
            visibility=Document.Visibility.FAMILY,
            title="no-membership-family",
        )
        suspended_family = self.document(
            family=self.suspended,
            owner_membership=self.owner_suspended,
            visibility=Document.Visibility.FAMILY,
            title="suspended-family",
        )

        queryset = visible_documents_for_user(
            self.viewer,
            [self.family_a.id, self.family_b.id, self.family_c.id, self.suspended.id],
        )
        with self.assertNumQueries(1):
            visible_ids = set(queryset.values_list("id", flat=True))

        self.assertEqual(
            visible_ids,
            {owned_private.id, family_visible.id, selected_view.id, selected_manage.id},
        )
        self.assertNotIn(foreign_private.id, visible_ids)
        self.assertNotIn(selected_other.id, visible_ids)
        self.assertNotIn(no_membership_family.id, visible_ids)
        self.assertNotIn(suspended_family.id, visible_ids)

    def test_archived_filter_is_explicit_and_single_family_wrapper_matches(self):
        active = self.document(
            family=self.family_a,
            owner_membership=self.owner_a,
            visibility=Document.Visibility.FAMILY,
            title="active-family-doc",
        )
        archived = self.document(
            family=self.family_a,
            owner_membership=self.owner_a,
            visibility=Document.Visibility.FAMILY,
            title="archived-family-doc",
            archived=True,
        )

        default_ids = set(
            visible_documents_for_user(self.viewer, [self.family_a.id]).values_list("id", flat=True)
        )
        archived_ids = set(
            visible_documents_for_user(
                self.viewer,
                [self.family_a.id],
                include_archived=True,
            ).values_list("id", flat=True)
        )
        wrapper_ids = set(
            visible_documents(self.viewer, self.family_a.id).values_list("id", flat=True)
        )

        self.assertEqual(default_ids, {active.id})
        self.assertEqual(wrapper_ids, default_ids)
        self.assertEqual(archived_ids, {active.id, archived.id})

    def test_anonymous_user_gets_empty_queryset(self):
        class Anonymous:
            is_authenticated = False

        self.assertFalse(
            visible_documents_for_user(Anonymous(), [self.family_a.id]).exists()
        )
