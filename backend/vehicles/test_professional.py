import uuid
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from entitlements.models import CapabilityDefinition
from family.models import Family, Membership

from .models import Journey, JourneyPoint, JourneyRevision, Vehicle


class ProfessionalLogbookTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.alice = user_model.objects.create_user(username="professional-alice")
        self.bob = user_model.objects.create_user(username="professional-bob")
        self.outsider = user_model.objects.create_user(username="professional-outsider")
        self.family = Family.objects.create(name="Professional Cars", slug="professional-cars")
        self.other_family = Family.objects.create(name="Other Cars", slug="other-professional-cars")
        Membership.objects.create(user=self.alice, family=self.family, role="owner")
        Membership.objects.create(user=self.bob, family=self.family, role="adult")
        Membership.objects.create(user=self.outsider, family=self.other_family, role="owner")
        CapabilityDefinition.objects.update_or_create(key="vehicles", defaults={"domain": "vehicles", "premium": True})
        self.vehicle = Vehicle.objects.create(family=self.family, name="Professional car", odometer=100)
        self.client = APIClient()
        self.client.force_authenticate(self.alice)
        self.journeys_url = f"/api/vehicles/{self.vehicle.id}/journeys/"

    def start_and_stop(self, *, end="110.0"):
        started = self.client.post(
            self.journeys_url,
            {"request_id": str(uuid.uuid4()), "start_odometer": "100.0"},
            format="json",
        )
        self.assertEqual(started.status_code, 201, started.data)
        detail = f"/api/vehicle-journeys/{started.data['id']}/"
        stopped = self.client.post(detail, {"end_odometer": end}, format="json")
        self.assertEqual(stopped.status_code, 200, stopped.data)
        return Journey.objects.get(pk=started.data["id"])

    def test_new_trip_enters_review_and_business_classification_is_revised(self):
        journey = self.start_and_stop()
        journey.refresh_from_db()
        self.assertEqual(journey.kind, "unclassified")
        self.assertTrue(journey.needs_review)
        self.assertIsNotNone(journey.review_due_at)
        self.assertAlmostEqual((journey.review_due_at - journey.ended_at).total_seconds(), 7 * 86400, delta=2)

        url = f"/api/vehicle-journeys/{journey.id}/classify/"
        missing = self.client.post(url, {"kind": "business", "purpose": "Meeting"}, format="json")
        self.assertEqual(missing.status_code, 400)
        self.assertIn("destination", missing.data)
        self.assertIn("business_partner", missing.data)

        classified = self.client.post(
            url,
            {
                "kind": "business",
                "destination": "Berlin",
                "business_partner": "Example GmbH",
                "purpose": "Projektbesprechung",
                "note": "Kundentermin",
            },
            format="json",
        )
        self.assertEqual(classified.status_code, 200, classified.data)
        self.assertFalse(classified.data["needs_review"])
        revision = JourneyRevision.objects.get(journey=journey, sequence=1)
        self.assertEqual(revision.event, "classified")
        self.assertEqual(revision.before["kind"], "unclassified")
        self.assertEqual(revision.after["kind"], "business")
        self.assertEqual(revision.after["business_partner"], "Example GmbH")

        no_reason = self.client.post(
            url,
            {
                "kind": "business",
                "destination": "Berlin",
                "business_partner": "Example GmbH",
                "purpose": "Geänderte Besprechung",
            },
            format="json",
        )
        self.assertEqual(no_reason.status_code, 400)
        self.assertIn("reason", no_reason.data)

        corrected = self.client.post(
            url,
            {
                "kind": "business",
                "destination": "Berlin",
                "business_partner": "Example GmbH",
                "purpose": "Geänderte Besprechung",
                "reason": "Zweck präzisiert",
            },
            format="json",
        )
        self.assertEqual(corrected.status_code, 200, corrected.data)
        revision = JourneyRevision.objects.get(journey=journey, sequence=2)
        self.assertEqual(revision.event, "corrected")
        self.assertEqual(revision.reason, "Zweck präzisiert")
        self.assertEqual(revision.before["purpose"], "Projektbesprechung")
        self.assertEqual(revision.after["purpose"], "Geänderte Besprechung")

    def test_review_deadline_requires_reason(self):
        journey = self.start_and_stop()
        journey.review_due_at = timezone.now() - timedelta(seconds=1)
        journey.save(update_fields=["review_due_at"])
        url = f"/api/vehicle-journeys/{journey.id}/classify/"

        no_reason = self.client.post(url, {"kind": "private"}, format="json")
        self.assertEqual(no_reason.status_code, 400)
        self.assertIn("reason", no_reason.data)

        with_reason = self.client.post(url, {"kind": "private", "reason": "Nach Frist geprüft"}, format="json")
        self.assertEqual(with_reason.status_code, 200, with_reason.data)
        self.assertFalse(with_reason.data["needs_review"])
        self.assertEqual(JourneyRevision.objects.get(journey=journey).reason, "Nach Frist geprüft")

    def test_correction_void_and_revision_privacy(self):
        journey = self.start_and_stop()
        classify_url = f"/api/vehicle-journeys/{journey.id}/classify/"
        self.assertEqual(self.client.post(classify_url, {"kind": "private"}, format="json").status_code, 200)
        correct_url = f"/api/vehicle-journeys/{journey.id}/correct/"

        self.assertEqual(self.client.post(correct_url, {"end_odometer": "111.0"}, format="json").status_code, 400)
        corrected = self.client.post(
            correct_url,
            {"end_odometer": "111.0", "reason": "Ablesefehler am Kilometerzähler"},
            format="json",
        )
        self.assertEqual(corrected.status_code, 200, corrected.data)
        self.assertEqual(corrected.data["end_odometer"], "111.0")
        self.assertEqual(JourneyRevision.objects.filter(journey=journey).count(), 2)

        detail_url = f"/api/vehicle-journeys/{journey.id}/"
        deleted = self.client.delete(detail_url)
        self.assertEqual(deleted.status_code, 409)
        self.assertTrue(Journey.objects.filter(pk=journey.id).exists())

        void_url = f"/api/vehicle-journeys/{journey.id}/void/"
        self.assertEqual(self.client.post(void_url, {}, format="json").status_code, 400)
        voided = self.client.post(void_url, {"reason": "Doppelt erfasst"}, format="json")
        self.assertEqual(voided.status_code, 200, voided.data)
        self.assertIsNotNone(voided.data["voided_at"])
        self.assertEqual(JourneyRevision.objects.filter(journey=journey).count(), 3)
        self.assertTrue(Journey.objects.filter(pk=journey.id).exists())

        self.client.force_authenticate(self.bob)
        revisions = self.client.get(f"/api/vehicle-journeys/{journey.id}/revisions/")
        self.assertEqual(revisions.status_code, 404)
        report = self.client.get(f"/api/vehicles/{self.vehicle.id}/journey-report/")
        self.assertEqual(report.status_code, 200)
        self.assertEqual(report.data["summary"]["count"], 0)

        self.client.force_authenticate(self.outsider)
        self.assertEqual(self.client.get(f"/api/vehicles/{self.vehicle.id}/journey-report/").status_code, 404)

    def test_manual_business_entry_is_audited_and_exports_exclude_gps(self):
        end = timezone.now() - timedelta(hours=2)
        start = end - timedelta(hours=1)
        payload = {
            "request_id": str(uuid.uuid4()),
            "started_at": start.isoformat(),
            "ended_at": end.isoformat(),
            "start_odometer": "100.0",
            "end_odometer": "112.5",
            "kind": "business",
            "destination": "Hamburg",
            "business_partner": "Kunde Nord",
            "purpose": '=HYPERLINK("https://example.invalid")',
            "note": "Nachtrag aus Beleg",
            "detour_reason": "Baustelle",
            "reason": "Browser war während der Fahrt nicht verfügbar",
        }
        response = self.client.post(f"/api/vehicles/{self.vehicle.id}/journeys/manual/", payload, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        journey = Journey.objects.get(pk=response.data["id"])
        self.assertEqual(journey.source, "manual")
        self.assertFalse(journey.legacy_record)
        self.assertEqual(JourneyRevision.objects.get(journey=journey).event, "manual_created")
        JourneyPoint.objects.create(
            journey=journey,
            sequence=0,
            timestamp=start + timedelta(minutes=1),
            latitude=52.520008,
            longitude=13.404954,
            accuracy=5,
        )

        csv_response = self.client.get(f"/api/vehicles/{self.vehicle.id}/journey-report/?format=csv")
        self.assertEqual(csv_response.status_code, 200)
        csv_text = csv_response.content.decode("utf-8-sig")
        self.assertIn("'=HYPERLINK", csv_text)
        self.assertNotIn("52.520008", csv_text)
        self.assertNotIn("13.404954", csv_text)
        self.assertNotIn("latitude", csv_text.lower())
        self.assertEqual(csv_response["Cache-Control"], "private, no-store")

        audit_response = self.client.get(f"/api/vehicles/{self.vehicle.id}/journey-report/?format=audit")
        self.assertEqual(audit_response.status_code, 200)
        audit_text = audit_response.content.decode("utf-8-sig")
        self.assertIn("manual_created", audit_text)
        self.assertNotIn("52.520008", audit_text)
        self.assertNotIn("13.404954", audit_text)

        pdf_response = self.client.get(f"/api/vehicles/{self.vehicle.id}/journey-report/?format=pdf")
        self.assertEqual(pdf_response.status_code, 200)
        self.assertEqual(pdf_response["Content-Type"], "application/pdf")
        self.assertTrue(pdf_response.content.startswith(b"%PDF"))

    def test_reports_cover_all_rows_while_history_stays_bounded(self):
        base = timezone.now() - timedelta(days=600)
        rows = []
        for index in range(501):
            started = base + timedelta(days=index)
            rows.append(Journey(
                vehicle=self.vehicle,
                driver=self.alice,
                request_id=uuid.uuid4(),
                started_at=started,
                ended_at=started + timedelta(hours=1),
                start_odometer=Decimal("100.0"),
                end_odometer=Decimal("101.0"),
                kind="private",
                classified_at=started + timedelta(hours=1),
            ))
        Journey.objects.bulk_create(rows)

        history = self.client.get(self.journeys_url)
        self.assertEqual(history.status_code, 200)
        self.assertEqual(len(history.data), 500)

        report = self.client.get(f"/api/vehicles/{self.vehicle.id}/journey-report/")
        self.assertEqual(report.status_code, 200)
        self.assertEqual(report.data["summary"]["count"], 501)
        self.assertEqual(report.data["summary"]["distance_km"], "501.0")

        exported = self.client.get(f"/api/vehicles/{self.vehicle.id}/journey-report/?format=csv")
        lines = exported.content.decode("utf-8-sig").splitlines()
        self.assertEqual(len(lines), 502)

    def test_business_suggestions_are_driver_private(self):
        now = timezone.now() - timedelta(days=1)
        Journey.objects.create(
            vehicle=self.vehicle,
            driver=self.alice,
            request_id=uuid.uuid4(),
            started_at=now,
            ended_at=now + timedelta(hours=1),
            start_odometer=100,
            end_odometer=101,
            kind="business",
            destination="Alice Ziel",
            business_partner="Alice Kunde",
            purpose="Alice Zweck",
        )
        Journey.objects.create(
            vehicle=self.vehicle,
            driver=self.bob,
            request_id=uuid.uuid4(),
            started_at=now,
            ended_at=now + timedelta(hours=1),
            start_odometer=101,
            end_odometer=102,
            kind="business",
            destination="Bob Geheimziel",
            business_partner="Bob Geheimkunde",
            purpose="Bob Geheimzweck",
        )
        response = self.client.get(f"/api/vehicles/{self.vehicle.id}/journey-suggestions/")
        self.assertEqual(response.status_code, 200)
        combined = " ".join(sum(response.data.values(), []))
        self.assertIn("Alice Ziel", combined)
        self.assertIn("Alice Kunde", combined)
        self.assertNotIn("Bob Geheimziel", combined)
        self.assertNotIn("Bob Geheimkunde", combined)
