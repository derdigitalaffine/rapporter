import uuid
from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError

from family.models import Family, Membership, UserProfile

from .care_service import record_care_log, update_care_log
from .development_service import development_payload, ensure_u_exam_events, record_observation
from .family_modules import care_access, set_care_circle, set_module
from .growth_service import corrected_age_days, growth_payload
from .models import BabyCareLog, BabyProfile, CareCircleAccess, FamilyModuleSetting, PregnancyJourney, ReportExportAudit
from .pregnancy_service import complete_birth, create_managed_child, create_pregnancy
from .report_service import audited_export


User = get_user_model()


class BabyDomainTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username="owner", password="pw")
        self.adult = User.objects.create_user(username="adult", password="pw")
        self.guest = User.objects.create_user(username="guest", password="pw")
        self.family = Family.objects.create(name="Familie", slug="familie-baby", timezone="Europe/Berlin")
        self.owner_membership = Membership.objects.create(family=self.family, user=self.owner, role=Membership.Role.OWNER, display_name="Owner")
        self.adult_membership = Membership.objects.create(family=self.family, user=self.adult, role=Membership.Role.ADULT, display_name="Adult")
        self.guest_membership = Membership.objects.create(family=self.family, user=self.guest, role=Membership.Role.GUEST, display_name="Guest")

    def enable(self):
        return set_module(self.owner, self.family, enabled=True)

    def add_adult_circle(self, *, care=True, growth=True, pregnancy=True):
        return CareCircleAccess.objects.create(
            family=self.family,
            membership=self.adult_membership,
            can_view_pregnancy=pregnancy,
            can_log_care=care,
            can_view_growth_development=growth,
            is_guardian=True,
        )

    def create_baby(self, **overrides):
        self.enable()
        data = {
            "display_name": "Mia",
            "birth_date": date.today() - timedelta(days=60),
            "growth_reference_sex": "female",
            "client_identity_key": uuid.uuid4(),
        }
        data.update(overrides)
        return create_managed_child(self.owner, self.family, **data)

    def test_module_is_off_by_default_and_sensitive_access_requires_care_circle(self):
        setting = FamilyModuleSetting.objects.create(family=self.family, module_key="pregnancy_baby")
        self.assertFalse(setting.enabled)
        with self.assertRaises(NotFound):
            care_access(self.owner, self.family, "pregnancy")
        self.enable()
        self.assertTrue(CareCircleAccess.objects.filter(family=self.family, membership=self.owner_membership, can_view_pregnancy=True).exists())
        with self.assertRaises(PermissionDenied):
            care_access(self.adult, self.family, "pregnancy")

    def test_care_circle_scope_is_explicit(self):
        self.enable()
        self.add_adult_circle(care=True, growth=False, pregnancy=False)
        care_access(self.adult, self.family, "care")
        with self.assertRaises(PermissionDenied):
            care_access(self.adult, self.family, "growth")
        with self.assertRaises(PermissionDenied):
            care_access(self.guest, self.family, "care")

    def test_multiple_birth_transition_creates_real_managed_child_identities_idempotently(self):
        self.enable()
        pregnancy = create_pregnancy(self.owner, self.family, expected_due_date=date.today() + timedelta(days=14), baby_count=2)
        expected = list(pregnancy.expected_babies.order_by("order_index"))
        payload = [
            {"pregnancy_baby": expected[0].id, "display_name": "Mia", "birth_date": date.today(), "gestational_age_weeks": 38, "gestational_age_days": 1, "growth_reference_sex": "female"},
            {"pregnancy_baby": expected[1].id, "display_name": "Noah", "birth_date": date.today(), "gestational_age_weeks": 38, "gestational_age_days": 1, "growth_reference_sex": "male"},
        ]
        babies = complete_birth(self.owner, pregnancy, payload)
        self.assertEqual(len(babies), 2)
        self.assertEqual(PregnancyJourney.objects.get(pk=pregnancy.pk).status, PregnancyJourney.Status.BIRTH_COMPLETED)
        for baby in babies:
            self.assertEqual(baby.membership.role, Membership.Role.CHILD)
            self.assertFalse(baby.membership.user.has_usable_password())
            self.assertEqual(baby.membership.user.email, "")
            profile = UserProfile.objects.get(user=baby.membership.user)
            self.assertEqual((profile.birth_year, profile.birth_month, profile.birth_day), (date.today().year, date.today().month, date.today().day))
        again = complete_birth(self.owner, pregnancy, payload)
        self.assertEqual({x.id for x in babies}, {x.id for x in again})
        self.assertEqual(BabyProfile.objects.filter(family=self.family).count(), 2)

    def test_disabling_module_does_not_remove_child_identity(self):
        baby = self.create_baby()
        user_id = baby.membership.user_id
        membership_id = baby.membership_id
        set_module(self.owner, self.family, enabled=False)
        self.assertTrue(User.objects.filter(pk=user_id).exists())
        self.assertTrue(Membership.objects.filter(pk=membership_id, role=Membership.Role.CHILD).exists())
        self.assertTrue(BabyProfile.objects.filter(pk=baby.pk).exists())

    def test_care_event_client_uuid_is_idempotent_and_versioned(self):
        baby = self.create_baby()
        event_id = uuid.uuid4()
        now = timezone.now()
        first, created = record_care_log(self.owner, baby.id, kind="bottle", started_at=now, value={"ml": 90}, client_event_id=event_id)
        second, created_again = record_care_log(self.owner, baby.id, kind="bottle", started_at=now, value={"ml": 90}, client_event_id=event_id)
        self.assertTrue(created)
        self.assertFalse(created_again)
        self.assertEqual(first.id, second.id)
        updated = update_care_log(self.owner, first.id, expected_version=1, value={"ml": 100})
        self.assertEqual(updated.version, 2)
        with self.assertRaises(ValidationError):
            update_care_log(self.owner, first.id, expected_version=1, value={"ml": 110})
        self.assertEqual(BabyCareLog.objects.filter(baby=baby).count(), 1)

    def test_corrected_age_and_growth_reference_are_explicit_and_non_diagnostic(self):
        baby = self.create_baby(
            birth_date=date.today() - timedelta(days=70),
            gestational_age_weeks=32,
            gestational_age_days=0,
            growth_reference_sex="unspecified",
        )
        measured = timezone.now()
        self.assertEqual(corrected_age_days(baby, measured), 14)
        payload = growth_payload(self.owner, baby.id)
        self.assertEqual(payload["reference"]["key"], "who_2006_corrected")
        self.assertIn("WHO", payload["reference"]["label"])
        self.assertIn("not a diagnosis", payload["interpretation"])

    def test_development_is_observational_and_preventive_events_are_idempotent(self):
        baby = self.create_baby(birth_date=date.today() - timedelta(days=120), gestational_age_weeks=40)
        data = development_payload(self.owner, baby.id, language="de")
        self.assertEqual(data["source"]["key"], "cdc_act_early")
        self.assertIn("not a score or diagnosis", data["interpretation"])
        key = data["items"][0]["key"]
        observation = record_observation(self.owner, baby.id, milestone_key=key, state="later")
        self.assertEqual(observation.state, "later")
        first = ensure_u_exam_events(self.owner, baby.id)
        second = ensure_u_exam_events(self.owner, baby.id)
        self.assertEqual([x.id for x in first], [x.id for x in second])

    def test_reports_are_scope_limited_and_audited(self):
        baby = self.create_baby()
        self.add_adult_circle(care=True, growth=False, pregnancy=False)
        record_care_log(self.adult, baby.id, kind="diaper", started_at=timezone.now(), value={"type": "wet"}, client_event_id=uuid.uuid4())
        payload, _, content_type = audited_export(self.adult, baby.id, export_format="json", sections=["care"])
        self.assertEqual(payload["sections"], ["care"])
        self.assertEqual(content_type, "application/json")
        self.assertEqual(ReportExportAudit.objects.filter(baby=baby, membership=self.adult_membership).count(), 1)
        with self.assertRaises(PermissionDenied):
            audited_export(self.adult, baby.id, export_format="json", sections=["growth"])
