from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from auth_identity.models import EmailIdentity
from family.models import Family, FamilyInvitation, Membership

from .models import UsageEvent


class SuperadminActivationRetentionTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.admin = User.objects.create_superuser(username="activation-admin", password="pw")
        self.client = APIClient()
        self.client.force_authenticate(self.admin)

    def _usage(self, *, user, family, occurred_at):
        UsageEvent.objects.create(
            user=user,
            family=family,
            event_key="activity.foreground",
            occurred_at=occurred_at,
            bucket_start=occurred_at.replace(minute=0, second=0, microsecond=0),
            dimension_key="",
        )

    def test_activation_requires_acceptance_verified_email_and_same_family_activity_within_seven_days(self):
        User = get_user_model()
        now = timezone.now()
        family = Family.objects.create(name="Activation Family", slug="activation-family")

        activated_user = User.objects.create_user(username="activated-user", password="pw")
        activated_at = now - timedelta(days=10)
        EmailIdentity.objects.create(
            user=activated_user,
            kind=EmailIdentity.Kind.PRIMARY,
            email="activated@example.test",
            email_normalized="activated@example.test",
            verified_at=activated_at + timedelta(hours=2),
        )
        Membership.objects.create(family=family, user=activated_user, role=Membership.Role.ADULT)
        FamilyInvitation.objects.create(
            family=family,
            role=Membership.Role.ADULT,
            email="activated@example.test",
            expires_at=now + timedelta(days=2),
            accepted_at=activated_at,
            accepted_by=activated_user,
        )
        self._usage(user=activated_user, family=family, occurred_at=activated_at + timedelta(days=2))

        no_activity_user = User.objects.create_user(username="no-activity-user", password="pw")
        no_activity_at = now - timedelta(days=9)
        EmailIdentity.objects.create(
            user=no_activity_user,
            kind=EmailIdentity.Kind.PRIMARY,
            email="no-activity@example.test",
            email_normalized="no-activity@example.test",
            verified_at=no_activity_at + timedelta(hours=1),
        )
        Membership.objects.create(family=family, user=no_activity_user, role=Membership.Role.ADULT)
        FamilyInvitation.objects.create(
            family=family,
            role=Membership.Role.ADULT,
            email="no-activity@example.test",
            expires_at=now + timedelta(days=2),
            accepted_at=no_activity_at,
            accepted_by=no_activity_user,
        )

        late_verification_user = User.objects.create_user(username="late-verification-user", password="pw")
        late_verification_at = now - timedelta(days=8)
        EmailIdentity.objects.create(
            user=late_verification_user,
            kind=EmailIdentity.Kind.PRIMARY,
            email="late-verification@example.test",
            email_normalized="late-verification@example.test",
            verified_at=late_verification_at + timedelta(days=8),
        )
        Membership.objects.create(family=family, user=late_verification_user, role=Membership.Role.ADULT)
        FamilyInvitation.objects.create(
            family=family,
            role=Membership.Role.ADULT,
            email="late-verification@example.test",
            expires_at=now + timedelta(days=2),
            accepted_at=late_verification_at,
            accepted_by=late_verification_user,
        )
        self._usage(user=late_verification_user, family=family, occurred_at=late_verification_at + timedelta(days=1))

        wrong_family = Family.objects.create(name="Wrong Family", slug="wrong-family")
        wrong_family_user = User.objects.create_user(username="wrong-family-user", password="pw")
        wrong_family_at = now - timedelta(days=7)
        EmailIdentity.objects.create(
            user=wrong_family_user,
            kind=EmailIdentity.Kind.PRIMARY,
            email="wrong-family@example.test",
            email_normalized="wrong-family@example.test",
            verified_at=wrong_family_at + timedelta(hours=1),
        )
        Membership.objects.create(family=family, user=wrong_family_user, role=Membership.Role.ADULT)
        FamilyInvitation.objects.create(
            family=family,
            role=Membership.Role.ADULT,
            email="wrong-family@example.test",
            expires_at=now + timedelta(days=2),
            accepted_at=wrong_family_at,
            accepted_by=wrong_family_user,
        )
        self._usage(user=wrong_family_user, family=wrong_family, occurred_at=wrong_family_at + timedelta(days=1))

        response = self.client.get("/api/superadmin/analytics/overview/?period=30d")

        self.assertEqual(response.status_code, 200, response.data)
        activation = response.data["onboarding"]["activation"]
        self.assertEqual(activation["definition_version"], "membership-v1")
        self.assertEqual(activation["window_days"], 7)
        self.assertEqual(activation["accepted_memberships"]["value"], 4)
        self.assertEqual(activation["email_verified"]["value"], 3)
        self.assertEqual(activation["meaningful_activity_within_7d"]["value"], 2)
        self.assertEqual(activation["activated"]["value"], 1)
        self.assertEqual(activation["activation_rate_pct"]["value"], 25.0)
        self.assertNotIn("email", str(response.data["retention"]))
        self.assertNotIn("user_id", str(response.data["retention"]))

    def test_d7_user_and_family_retention_uses_exact_day_window_and_reports_mature_n(self):
        User = get_user_model()
        now = timezone.now()
        cohort_at = now - timedelta(days=15)
        retained_users = 3

        for index in range(5):
            user = User.objects.create_user(username=f"retention-user-{index}", password="pw")
            User.objects.filter(pk=user.pk).update(date_joined=cohort_at + timedelta(minutes=index))
            user.refresh_from_db()
            family = Family.objects.create(name=f"Retention Family {index}", slug=f"retention-family-{index}")
            Family.objects.filter(pk=family.pk).update(created_at=cohort_at + timedelta(minutes=index))
            family.refresh_from_db()
            Membership.objects.create(family=family, user=user, role=Membership.Role.OWNER)

            if index < retained_users:
                self._usage(
                    user=user,
                    family=family,
                    occurred_at=user.date_joined + timedelta(days=7, hours=3),
                )

        response = self.client.get("/api/superadmin/analytics/overview/?period=30d")

        self.assertEqual(response.status_code, 200, response.data)
        user_d7 = response.data["retention"]["users"]["d7"]
        family_d7 = response.data["retention"]["families"]["d7"]
        self.assertEqual(user_d7["eligible"]["value"], 5)
        self.assertEqual(user_d7["retained"]["value"], 3)
        self.assertEqual(user_d7["rate_pct"]["value"], 60.0)
        self.assertFalse(user_d7["small_cohort_suppressed"])
        self.assertEqual(family_d7["eligible"]["value"], 5)
        self.assertEqual(family_d7["retained"]["value"], 3)
        self.assertEqual(family_d7["rate_pct"]["value"], 60.0)
        self.assertFalse(family_d7["small_cohort_suppressed"])

    def test_small_mature_retention_cohort_suppresses_rate_but_keeps_counts(self):
        User = get_user_model()
        now = timezone.now()
        joined = now - timedelta(days=12)
        for index in range(3):
            user = User.objects.create_user(username=f"small-retention-{index}", password="pw")
            User.objects.filter(pk=user.pk).update(date_joined=joined + timedelta(minutes=index))
            user.refresh_from_db()
            family = Family.objects.create(name=f"Small Family {index}", slug=f"small-family-{index}")
            self._usage(
                user=user,
                family=family,
                occurred_at=user.date_joined + timedelta(days=7, hours=1),
            )

        response = self.client.get("/api/superadmin/analytics/overview/?period=30d")

        self.assertEqual(response.status_code, 200, response.data)
        user_d7 = response.data["retention"]["users"]["d7"]
        self.assertEqual(user_d7["eligible"]["value"], 3)
        self.assertEqual(user_d7["retained"]["value"], 3)
        self.assertIsNone(user_d7["rate_pct"]["value"])
        self.assertTrue(user_d7["small_cohort_suppressed"])

    def test_activation_does_not_count_verification_or_activity_after_snapshot(self):
        from .superadmin_views import _activation_metrics
        User = get_user_model()
        snapshot = timezone.now()
        family = Family.objects.create(name="Snapshot", slug="snapshot")
        for index in range(2):
            user = User.objects.create_user(username=f"snapshot-{index}")
            accepted = snapshot - timedelta(days=1)
            EmailIdentity.objects.create(
                user=user, kind=EmailIdentity.Kind.PRIMARY,
                email=f"snapshot-{index}@example.test", email_normalized=f"snapshot-{index}@example.test",
                verified_at=snapshot + timedelta(hours=1) if index == 0 else accepted,
            )
            FamilyInvitation.objects.create(
                family=family, role=Membership.Role.ADULT, email=f"snapshot-{index}@example.test",
                expires_at=snapshot + timedelta(days=2), accepted_at=accepted, accepted_by=user,
            )
            self._usage(user=user, family=family, occurred_at=accepted if index == 0 else snapshot + timedelta(hours=1))
        with self.assertNumQueries(1):
            metrics = _activation_metrics(snapshot - timedelta(days=30), snapshot)
        self.assertEqual(metrics["accepted_memberships"], 2)
        self.assertEqual(metrics["email_verified"], 1)
        self.assertEqual(metrics["meaningful_activity_within_7d"], 1)
        self.assertEqual(metrics["activated"], 0)

    def test_retention_has_constant_single_query_per_cohort_and_horizon(self):
        from .superadmin_views import _user_retention, _family_retention
        snapshot = timezone.now()
        with self.assertNumQueries(1):
            users = _user_retention(snapshot - timedelta(days=30), snapshot, 7)
        with self.assertNumQueries(1):
            families = _family_retention(snapshot - timedelta(days=30), snapshot, 7)
        self.assertEqual(users["eligible"], 0)
        self.assertIsNone(families["rate_pct"])
