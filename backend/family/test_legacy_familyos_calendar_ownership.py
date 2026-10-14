import importlib

from django.apps import apps
from django.contrib.auth import get_user_model
from django.test import TestCase

from .models import Family, FamilyEvent, IntegrationSource, Membership


class LegacyFamilyOsCalendarOwnershipTests(TestCase):
    def setUp(self):
        user = get_user_model().objects.create_user(username="legacy-calendar-owner")
        self.family = Family.objects.create(name="Legacy Calendar", slug="legacy-calendar")
        Membership.objects.create(family=self.family, user=user, role="owner")
        self.source = IntegrationSource.objects.create(
            family=self.family,
            name="Historische Kalenderquelle",
            kind="ics",
        )

    def event(self, *, provider="FamilyOS", external_id=""):
        return FamilyEvent.objects.create(
            family=self.family,
            source=self.source,
            type="calendar.event",
            title="Alttermin",
            payload={"provider": provider},
            external_id=external_id,
        )

    def run_migration(self):
        migration = importlib.import_module("family.migrations.0236_legacy_familyos_calendar_ownership")
        migration.detach_stale_familyos_sources(apps, None)

    def test_detaches_stale_source_from_legacy_familyos_event(self):
        event = self.event()
        self.run_migration()
        event.refresh_from_db()
        self.assertIsNone(event.source_id)

    def test_keeps_real_import_with_external_id_source_owned(self):
        event = self.event(external_id="ics:real-import")
        self.run_migration()
        event.refresh_from_db()
        self.assertEqual(event.source_id, self.source.id)

    def test_keeps_non_familyos_source_owned(self):
        event = self.event(provider="External")
        self.run_migration()
        event.refresh_from_db()
        self.assertEqual(event.source_id, self.source.id)
