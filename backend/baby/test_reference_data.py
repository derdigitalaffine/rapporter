import uuid
from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError as DjangoValidationError
from django.test import TestCase
from rest_framework.exceptions import PermissionDenied, ValidationError

from family.models import Family, Membership
from telemetry.models import AuditEvent

from .development_service import ensure_u_exam_events
from .family_modules import set_module
from .pregnancy_service import create_managed_child
from .reference_models import PediatricPreventiveEventReference, PediatricReferencePackage
from .reference_service import (
    DEFAULT_SOURCE_KEY,
    create_reference_draft,
    payload_checksum,
    publish_reference_package,
    published_reference_package,
    reactivate_reference_package,
    update_reference_draft,
    validate_reference_package,
)


User = get_user_model()


def reference_payload(*, exam_target=6, bad_sequence=False):
    return {
        "schema_version": 1,
        "u_exams": [
            {
                "key": "U2",
                "age_window": {"start_day": 3, "end_day": 10, "target_day": exam_target},
                "display": {"de": "U2", "window_label": "3.–10. Lebenstag"},
                "source_url": "https://example.invalid/u2",
            }
        ],
        "vaccinations": [
            {
                "key": "standard_series",
                "display": {"de": "Standardimpfung"},
                "doses": [
                    {"sequence": 1, "age_window": {"start_day": 42, "end_day": 84}, "min_interval_days": 0},
                    {"sequence": 1 if bad_sequence else 2, "age_window": {"start_day": 84, "end_day": 140}, "min_interval_days": 28},
                ],
                "boosters": [{"age_window": {"start_day": 330, "end_day": 450}}],
            }
        ],
    }


class PediatricReferenceTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser(username="reference-admin", password="pw", email="admin@example.invalid")
        self.owner = User.objects.create_user(username="reference-owner", password="pw")
        self.family = Family.objects.create(name="Reference Family", slug="reference-family", timezone="Europe/Berlin", locale="de")
        Membership.objects.create(family=self.family, user=self.owner, role=Membership.Role.OWNER, display_name="Owner")
        set_module(self.owner, self.family, enabled=True)

    def draft(self, version="2026.1", effective_from=date(2026, 1, 1), **payload_kwargs):
        return create_reference_draft(
            self.admin,
            source_key=DEFAULT_SOURCE_KEY,
            source_title="Reviewed pediatric standard",
            source_version=version,
            locale="de-DE",
            effective_from=effective_from,
            payload=reference_payload(**payload_kwargs),
            reason="reviewed release",
            notes="Controlled import for tests.",
        )

    def baby(self, name="Mia"):
        return create_managed_child(
            self.owner,
            self.family,
            display_name=name,
            birth_date=date.today(),
            growth_reference_sex="female",
            client_identity_key=uuid.uuid4(),
        )

    def test_only_superadmin_can_create_or_mutate_reference_packages(self):
        with self.assertRaises(PermissionDenied):
            create_reference_draft(
                self.owner,
                source_key=DEFAULT_SOURCE_KEY,
                source_title="Nope",
                source_version="1",
                payload=reference_payload(),
            )
        package = self.draft()
        publish_reference_package(self.admin, package.id)
        with self.assertRaises(ValidationError):
            update_reference_draft(package, self.admin, notes="silent rewrite")

    def test_invalid_age_and_dose_rules_cannot_publish(self):
        package = self.draft()
        package.payload = reference_payload(bad_sequence=True)
        package.checksum = payload_checksum(package.payload)
        package.save()
        with self.assertRaises(ValidationError):
            publish_reference_package(self.admin, package.id)

        other = self.draft(version="2026.2")
        other.payload["u_exams"][0]["age_window"] = {"start_day": 10, "end_day": 3}
        other.checksum = payload_checksum(other.payload)
        other.save()
        with self.assertRaises(ValidationError):
            validate_reference_package(other)

    def test_published_payload_is_immutable_and_delete_is_blocked(self):
        package = publish_reference_package(self.admin, self.draft().id)
        package.notes = "changed after publish"
        with self.assertRaises(DjangoValidationError):
            package.save()
        package.refresh_from_db()
        with self.assertRaises(DjangoValidationError):
            package.delete()

    def test_future_effective_package_cannot_displace_current_release_early(self):
        current = publish_reference_package(self.admin, self.draft("2026.1").id)
        future = self.draft("2026.2", effective_from=date.today() + timedelta(days=30), exam_target=8)
        with self.assertRaises(DjangoValidationError):
            publish_reference_package(self.admin, future.id)
        future.refresh_from_db()
        current.refresh_from_db()
        self.assertEqual(future.status, PediatricReferencePackage.Status.DRAFT)
        self.assertEqual(current.status, PediatricReferencePackage.Status.PUBLISHED)
        self.assertEqual(published_reference_package().id, current.id)

    def test_publish_supersede_reactivate_and_audit(self):
        first = publish_reference_package(self.admin, self.draft("2026.1").id)
        second = publish_reference_package(self.admin, self.draft("2026.2", exam_target=7).id)
        first.refresh_from_db()
        self.assertEqual(first.status, PediatricReferencePackage.Status.SUPERSEDED)
        self.assertEqual(first.superseded_by_id, second.id)
        self.assertEqual(published_reference_package().id, second.id)

        reactivated = reactivate_reference_package(self.admin, first.id)
        second.refresh_from_db()
        self.assertEqual(reactivated.status, PediatricReferencePackage.Status.PUBLISHED)
        self.assertEqual(second.status, PediatricReferencePackage.Status.SUPERSEDED)
        self.assertTrue(AuditEvent.objects.filter(event_key="pediatric_reference.published", target_id=str(first.id)).exists())
        self.assertTrue(AuditEvent.objects.filter(event_key="pediatric_reference.reactivated", target_id=str(first.id)).exists())

    def test_preventive_event_keeps_private_reference_version_that_created_it(self):
        first = publish_reference_package(self.admin, self.draft("2026.1").id)
        baby = self.baby()
        events = ensure_u_exam_events(self.owner, baby.id)
        self.assertEqual(len(events), 1)
        event = events[0]
        self.assertNotIn("pediatric_reference", event.payload)
        provenance = PediatricPreventiveEventReference.objects.get(event=event)
        self.assertEqual(provenance.baby_id, baby.id)
        self.assertEqual(provenance.reference_package_id, first.id)
        self.assertEqual(provenance.source_version, "2026.1")
        self.assertEqual(provenance.rule_key, "U2")

        second = publish_reference_package(self.admin, self.draft("2026.2", exam_target=8).id)
        repeated = ensure_u_exam_events(self.owner, baby.id)
        self.assertEqual(repeated[0].id, event.id)
        provenance.refresh_from_db()
        self.assertEqual(provenance.reference_package_id, first.id)
        self.assertEqual(provenance.target_day, 6)

        newer_baby = self.baby("Noah")
        newer_event = ensure_u_exam_events(self.owner, newer_baby.id)[0]
        newer_provenance = PediatricPreventiveEventReference.objects.get(event=newer_event)
        self.assertEqual(newer_provenance.reference_package_id, second.id)
        self.assertEqual(newer_provenance.target_day, 8)