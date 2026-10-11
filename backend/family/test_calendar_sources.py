from django.test import TestCase

from .models import Family, FamilyEvent, IntegrationSource
from .serializers import FamilyEventSerializer, IntegrationSourceSerializer


class CalendarSourcePresentationTests(TestCase):
    def setUp(self):
        self.family = Family.objects.create(name="Source family", slug="source-family")
        self.source = IntegrationSource.objects.create(
            family=self.family,
            name="Schulkalender",
            kind=IntegrationSource.Kind.ICS,
            endpoint="https://calendar.example.test/private.ics",
            config={"api_key": "secret-value", "adapter": "ics_url"},
        )

    def test_serializer_accepts_and_normalizes_allowlisted_presentation(self):
        serializer = IntegrationSourceSerializer(
            self.source,
            data={
                "config": {
                    "adapter": "ics_url",
                    "calendar_presentation": {
                        "icon": "school",
                        "tone": "violet",
                        "label": "  Schule  ",
                    },
                }
            },
            partial=True,
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)
        source = serializer.save()
        self.assertEqual(
            source.config["calendar_presentation"],
            {"icon": "school", "tone": "violet", "label": "Schule"},
        )

    def test_serializer_rejects_untrusted_presentation_values(self):
        cases = [
            {"icon": "script"},
            {"tone": "#ff00ff"},
            {"label": "x" * 81},
            {"label": "bad\nlabel"},
            {"unknown": "value"},
        ]
        for presentation in cases:
            with self.subTest(presentation=presentation):
                serializer = IntegrationSourceSerializer(
                    self.source,
                    data={"config": {"calendar_presentation": presentation}},
                    partial=True,
                )
                self.assertFalse(serializer.is_valid())
                self.assertIn("config", serializer.errors)

    def test_source_response_keeps_secrets_redacted(self):
        self.source.config = {
            "api_key": "secret-value",
            "calendar_presentation": {"icon": "calendar", "tone": "teal", "label": "Privat"},
        }
        self.source.save(update_fields=["config", "updated_at"])

        data = IntegrationSourceSerializer(self.source).data

        self.assertEqual(data["config"]["api_key"], "••••••••")
        self.assertEqual(
            data["config"]["calendar_presentation"],
            {"icon": "calendar", "tone": "teal", "label": "Privat"},
        )

    def test_family_event_exposes_only_safe_source_metadata(self):
        self.source.config = {
            "api_key": "secret-value",
            "client_secret": "another-secret",
            "calendar_presentation": {"icon": "school", "tone": "violet", "label": "Schule"},
        }
        self.source.save(update_fields=["config", "updated_at"])
        event = FamilyEvent.objects.create(
            family=self.family,
            source=self.source,
            type="ics",
            title="Elternabend",
            external_id="event-1",
        )

        data = FamilyEventSerializer(event).data

        self.assertEqual(
            data["source_meta"],
            {
                "id": str(self.source.id),
                "name": "Schulkalender",
                "kind": "ics",
                "presentation": {"icon": "school", "tone": "violet", "label": "Schule"},
            },
        )
        self.assertNotIn("config", data["source_meta"])
        self.assertNotIn("endpoint", data["source_meta"])

    def test_legacy_invalid_presentation_is_not_reflected(self):
        self.source.config = {
            "calendar_presentation": {
                "icon": "not-an-icon",
                "tone": "url(javascript:bad)",
                "label": "Legacy source",
                "extra": "ignored",
            }
        }
        self.source.save(update_fields=["config", "updated_at"])
        event = FamilyEvent.objects.create(
            family=self.family,
            source=self.source,
            type="ics",
            title="Legacy",
        )

        data = FamilyEventSerializer(event).data

        self.assertEqual(data["source_meta"]["presentation"], {"label": "Legacy source"})
