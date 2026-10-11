import threading
import uuid
from datetime import date

from django.contrib.auth import get_user_model
from django.db import close_old_connections
from django.test import TestCase, TransactionTestCase
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.test import APIClient

from auth_identity.models import EmailIdentity
from auth_identity.service import authenticate_identifier, verification_token, verify_email_token
from family.invitation_service import issue_invitation
from family.models import Family, Membership, UserProfile

from .child_identity_service import (
    begin_child_login_activation,
    child_login_is_active,
    reconcile_orphan_child_identities,
    replace_child_guardians,
    require_child_guardian,
)
from .family_modules import care_access, set_module
from .models import BabyProfile, CareCircleAccess, ManagedChildGuardian
from .pregnancy_service import create_managed_child


User = get_user_model()
PASSWORD = "correct-horse-battery-staple-236"


class ChildIdentityTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username="owner-236", password=PASSWORD)
        self.other_owner = User.objects.create_user(username="other-owner-236", password=PASSWORD)
        self.caregiver = User.objects.create_user(username="caregiver-236", password=PASSWORD)
        self.outsider = User.objects.create_user(username="outsider-236", password=PASSWORD)
        self.family = Family.objects.create(name="Child Family", slug="child-family-236")
        self.other_family = Family.objects.create(name="Other Family", slug="other-family-236")
        self.owner_membership = Membership.objects.create(family=self.family, user=self.owner, role=Membership.Role.OWNER, display_name="Owner")
        self.other_owner_membership = Membership.objects.create(family=self.family, user=self.other_owner, role=Membership.Role.OWNER, display_name="Other owner")
        self.caregiver_membership = Membership.objects.create(family=self.family, user=self.caregiver, role=Membership.Role.ADULT, display_name="Caregiver")
        self.outsider_membership = Membership.objects.create(family=self.other_family, user=self.outsider, role=Membership.Role.OWNER, display_name="Outsider")
        set_module(self.owner, self.family, enabled=True)
        self.baby = create_managed_child(
            self.owner,
            self.family,
            display_name="Mia",
            birth_date=date(2022, 4, 5),
            client_identity_key=uuid.uuid4(),
        )

    def test_managed_child_exists_without_login_credentials(self):
        child_user = self.baby.membership.user
        self.assertEqual(self.baby.membership.role, Membership.Role.CHILD)
        self.assertFalse(child_user.has_usable_password())
        self.assertEqual(child_user.email, "")
        self.assertFalse(EmailIdentity.objects.filter(user=child_user).exists())
        profile = UserProfile.objects.get(user=child_user)
        self.assertEqual((profile.birth_year, profile.birth_month, profile.birth_day), (2022, 4, 5))

    def test_owner_role_and_care_circle_do_not_imply_child_guardian(self):
        with self.assertRaises(PermissionDenied):
            require_child_guardian(self.other_owner, self.baby, manage=True)

        CareCircleAccess.objects.create(
            family=self.family,
            membership=self.caregiver_membership,
            can_log_care=True,
            can_view_growth_development=True,
            is_guardian=False,
        )
        care_access(self.caregiver, self.family, "care")
        with self.assertRaises(PermissionDenied):
            require_child_guardian(self.caregiver, self.baby, manage=True)

        self.assertTrue(
            ManagedChildGuardian.objects.filter(
                baby=self.baby,
                membership=self.owner_membership,
                can_manage_account=True,
            ).exists()
        )

    def test_guardians_are_child_specific_and_cross_family_targets_are_rejected(self):
        updated = replace_child_guardians(
            self.owner,
            self.baby.id,
            [
                {"membership": self.owner_membership.id, "can_manage_account": True},
                {"membership": self.other_owner_membership.id, "can_manage_account": True},
            ],
        )
        require_child_guardian(self.other_owner, updated, manage=True)
        with self.assertRaises(ValidationError):
            replace_child_guardians(
                self.owner,
                self.baby.id,
                [{"membership": self.outsider_membership.id, "can_manage_account": True}],
            )

        sibling = create_managed_child(
            self.owner,
            self.family,
            display_name="Noah",
            birth_date=date(2020, 1, 2),
            client_identity_key=uuid.uuid4(),
        )
        ManagedChildGuardian.objects.filter(baby=sibling, membership=self.other_owner_membership).delete()
        with self.assertRaises(PermissionDenied):
            require_child_guardian(self.other_owner, sibling, manage=True)

    def test_login_activation_reuses_child_user_and_requires_email_verification(self):
        child_user_id = self.baby.membership.user_id
        child_username = self.baby.membership.user.username
        user_count = User.objects.count()
        baby, identity = begin_child_login_activation(
            self.owner,
            self.baby.id,
            email="mia@example.test",
            password=PASSWORD,
        )
        self.assertEqual(baby.membership.user_id, child_user_id)
        self.assertEqual(User.objects.count(), user_count)
        self.assertEqual(identity.kind, EmailIdentity.Kind.PENDING)
        self.assertIsNone(authenticate_identifier("mia@example.test", PASSWORD))
        self.assertIsNone(authenticate_identifier(child_username, PASSWORD, legacy=True))
        self.assertFalse(child_login_is_active(baby))

        token = verification_token(identity)
        verified, changed = verify_email_token(token, locale="de")
        self.assertTrue(changed)
        self.assertEqual(verified.user_id, child_user_id)
        baby.refresh_from_db()
        self.assertTrue(child_login_is_active(baby))
        self.assertEqual(authenticate_identifier("mia@example.test", PASSWORD).pk, child_user_id)
        self.assertIsNone(authenticate_identifier(child_username, PASSWORD, legacy=True))
        self.assertEqual(User.objects.count(), user_count)

    def test_ordinary_invite_registration_cannot_duplicate_pending_child_identity(self):
        child_user_id = self.baby.membership.user_id
        begin_child_login_activation(
            self.owner,
            self.baby.id,
            email="mia-invite@example.test",
            password=PASSWORD,
        )
        invite, raw_token = issue_invitation(
            family=self.family,
            invited_by=self.owner,
            role=Membership.Role.TEEN,
            email="mia-invite@example.test",
            display_name="Mia",
        )
        count_before = User.objects.count()
        response = APIClient().post(
            f"/api/invite/{raw_token}/register/",
            {"email": "mia-invite@example.test", "password": PASSWORD, "display_name": "Mia"},
            format="json",
        )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(User.objects.count(), count_before)
        self.assertTrue(User.objects.filter(pk=child_user_id).exists())
        invite.refresh_from_db()
        self.assertIsNone(invite.accepted_at)

    def test_disabling_module_preserves_child_identity_and_guardians(self):
        child_user_id = self.baby.membership.user_id
        guardian_id = self.baby.guardians.get(membership=self.owner_membership).id
        set_module(self.owner, self.family, enabled=False)
        self.assertTrue(User.objects.filter(pk=child_user_id).exists())
        self.assertTrue(Membership.objects.filter(pk=self.baby.membership_id, role=Membership.Role.CHILD).exists())
        self.assertTrue(BabyProfile.objects.filter(pk=self.baby.pk, membership_id=self.baby.membership_id).exists())
        self.assertTrue(ManagedChildGuardian.objects.filter(pk=guardian_id).exists())

    def test_legacy_reconcile_is_idempotent_and_ambiguous_rows_require_review(self):
        orphan = BabyProfile.objects.create(
            family=self.family,
            display_name="Legacy Child",
            birth_date=date(2019, 3, 4),
            created_by=self.owner,
        )
        dry_run = reconcile_orphan_child_identities(apply=False)
        self.assertIn(str(orphan.id), dry_run["reconciled"])
        applied = reconcile_orphan_child_identities(apply=True)
        self.assertIn(str(orphan.id), applied["reconciled"])
        orphan.refresh_from_db()
        self.assertIsNotNone(orphan.membership_id)
        self.assertFalse(orphan.membership.user.has_usable_password())
        self.assertEqual(reconcile_orphan_child_identities(apply=True), {"reconciled": [], "review": []})

        first = BabyProfile.objects.create(family=self.family, display_name="Duplicate", birth_date=date(2018, 1, 1), created_by=self.owner)
        second = BabyProfile.objects.create(family=self.family, display_name="duplicate", birth_date=date(2018, 1, 1), created_by=self.owner)
        review = reconcile_orphan_child_identities(apply=True)
        self.assertEqual(set(review["review"]), {str(first.id), str(second.id)})
        first.refresh_from_db(); second.refresh_from_db()
        self.assertIsNone(first.membership_id)
        self.assertIsNone(second.membership_id)

    def test_legacy_reconcile_does_not_duplicate_linked_identity_or_infer_guardian(self):
        user_count = User.objects.count()
        duplicate_of_linked = BabyProfile.objects.create(
            family=self.family,
            display_name=" MIA ",
            birth_date=date(2022, 4, 5),
            created_by=self.owner,
        )
        no_guardian_seed = BabyProfile.objects.create(
            family=self.other_family,
            display_name="Legacy Other",
            birth_date=date(2017, 2, 3),
            created_by=self.outsider,
        )
        result = reconcile_orphan_child_identities(apply=True)
        self.assertIn(str(duplicate_of_linked.id), result["review"])
        self.assertIn(str(no_guardian_seed.id), result["review"])
        duplicate_of_linked.refresh_from_db(); no_guardian_seed.refresh_from_db()
        self.assertIsNone(duplicate_of_linked.membership_id)
        self.assertIsNone(no_guardian_seed.membership_id)
        self.assertEqual(User.objects.count(), user_count)


class ChildIdentityConcurrencyTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        self.owner = User.objects.create_user(username="owner-concurrent-236", password=PASSWORD)
        self.family = Family.objects.create(name="Concurrency Family", slug="child-concurrency-236")
        Membership.objects.create(family=self.family, user=self.owner, role=Membership.Role.OWNER, display_name="Owner")
        set_module(self.owner, self.family, enabled=True)

    def test_concurrent_manual_child_create_leaves_exactly_one_identity(self):
        identity_key = uuid.uuid4()
        barrier = threading.Barrier(2)
        results = []
        errors = []

        def worker():
            close_old_connections()
            try:
                owner = User.objects.get(pk=self.owner.pk)
                family = Family.objects.get(pk=self.family.pk)
                barrier.wait(timeout=5)
                row = create_managed_child(
                    owner,
                    family,
                    display_name="Concurrent Child",
                    birth_date=date(2021, 6, 7),
                    client_identity_key=identity_key,
                )
                results.append(str(row.pk))
            except Exception as exc:  # one loser may hit the DB uniqueness boundary
                errors.append(exc)
            finally:
                close_old_connections()

        threads = [threading.Thread(target=worker) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=10)

        self.assertEqual(BabyProfile.objects.filter(client_identity_key=identity_key).count(), 1)
        baby = BabyProfile.objects.get(client_identity_key=identity_key)
        self.assertEqual(Membership.objects.filter(pk=baby.membership_id, role=Membership.Role.CHILD).count(), 1)
        self.assertEqual(UserProfile.objects.filter(user_id=baby.membership.user_id).count(), 1)
        self.assertEqual(User.objects.filter(pk=baby.membership.user_id).count(), 1)
        self.assertTrue(results or errors)
