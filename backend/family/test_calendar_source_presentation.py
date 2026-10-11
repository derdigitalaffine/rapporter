from django.test import TestCase

from .models import Family, FamilyEvent, IntegrationSource
from .serializers import FamilyEventSerializer, IntegrationSourceSerializer


class CalendarSourcePresentationTests(TestCase):
    def setUp(self):
        self.family = Family.objects.create(name="Source Family", slug="calendar-source-family")

    def source_payload(self, **config):
        return {
            "family": str(self.family.id),
            "name": "Privatkalender",
            "kind": IntegrationSource.Kind.ICS,
            "config": config,
            "enabled": True,
        }

    def test_presentation_is_validated_and_normalized(self):
        serializer = IntegrationSourceSerializer(data=self.source_payload(
            presentation={"icon": "members", "color": "teal", "label": "  Privat  "},
        ))
        self.assertTrue(serializer.is_valid(), serializer.errors)
        source = serializer.save()
        self.assertEqual(source.config["presentation"], {"icon": "members", "color": "teal", "label": "Privat"})
        self.assertEqual(serializer.data["presentation"], {"icon": "members", "color": "teal", "label": "Privat"})

    def test_unsafe_or_unknown_presentation_values_are_rejected(self):
        for presentation in (
            {"icon": "<script>"},
            {"color": "#ff00ff"},
            {"css": "position:fixed"},
            {"label": "x" * 81},
        ):
            serializer = IntegrationSourceSerializer(data=self.source_payload(presentation=presentation))
            self.assertFalse(serializer.is_valid(), presentation)
            self.assertIn("config", serializer.errors)

    def test_legacy_source_without_presentation_keeps_stable_defaults(self):
        source = IntegrationSource.objects.create(
            family=self.family,
            name="Alter Familienkalender",
            kind=IntegrationSource.Kind.ICS,
            config={"refresh_minutes": 60},
        )
        data = IntegrationSourceSerializer(source).data
        self.assertEqual(data["presentation"], {"icon": "calendar", "color": "blue", "label": "Alter Familienkalender"})
        self.assertNotIn("presentation", data["config"])

    def test_event_projection_exposes_safe_named_source_metadata(self):
        first = IntegrationSource.objects.create(
            family=self.family,
            name="Eltern",
            kind=IntegrationSource.Kind.ICS,
            config={"presentation": {"icon": "members", "color": "green", "label": "Elternkalender"}},
        )
        second = IntegrationSource.objects.create(
            family=self.family,
            name="Kinder",
            kind=IntegrationSource.Kind.ICS,
            config={},
        )
        first_event = FamilyEvent.objects.create(family=self.family, source=first, type="calendar.event", title="Elterntermin")
        second_event = FamilyEvent.objects.create(family=self.family, source=second, type="calendar.event", title="Kindertermin")

        first_data = FamilyEventSerializer(first_event).data
        second_data = FamilyEventSerializer(second_event).data

        self.assertNotEqual(first_data["source"], second_data["source"])
        self.assertEqual(first_data["source_name"], "Eltern")
        self.assertEqual(first_data["source_kind"], "ics")
        self.assertEqual(first_data["source_presentation"], {"icon": "members", "color": "green", "label": "Elternkalender"})
        self.assertEqual(second_data["source_presentation"], {"icon": "calendar", "color": "blue", "label": "Kinder"})
