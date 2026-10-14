from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIRequestFactory, force_authenticate

from .calendar_views import FamilyEventViewSet, _is_externally_managed_event
from .models import Family, FamilyEvent, IntegrationSource, Membership


class LegacyCalendarSourceCompatibilityTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="legacy-calendar-owner", password="test")
        self.family = Family.objects.create(name="Legacy calendar", slug="legacy-calendar")
        Membership.objects.create(family=self.family, user=self.user, role=Membership.Role.OWNER)
        self.factory = APIRequestFactory()

    def _patch(self, event, payload):
        request = self.factory.patch(f"/events/{event.id}/", payload, format="json")
        force_authenticate(request, user=self.user)
        view = FamilyEventViewSet.as_view({"patch": "partial_update"})
        return view(request, pk=event.id)

    def test_generic_source_without_external_id_is_legacy_app_owned_and_self_heals_on_edit(self):
        source = IntegrationSource.objects.create(
            family=self.family,
            name="FamilyOS legacy",
            kind=IntegrationSource.Kind.GENERIC,
        )
        event = FamilyEvent.objects.create(
            family=self.family,
            source=source,
            type="calendar.legacy",
            title="Kinderarzt",
            external_id="",
            payload={"description": "Altbestand"},
        )

        self.assertFalse(_is_externally_managed_event(event))
        response = self._patch(event, {"title": "Kinderarzt neu"})

        self.assertEqual(response.status_code, 200, response.data)
        event.refresh_from_db()
        self.assertEqual(event.title, "Kinderarzt neu")
        self.assertIsNone(event.source_id)

    def test_known_integration_kind_stays_read_only_without_external_id(self):
        source = IntegrationSource.objects.create(
            family=self.family,
            name="ICS import",
            kind=IntegrationSource.Kind.ICS,
        )
        event = FamilyEvent.objects.create(
            family=self.family,
            source=source,
            type="calendar.event",
            title="Imported",
            external_id="",
        )

        self.assertTrue(_is_externally_managed_event(event))
        response = self._patch(event, {"title": "Should fail"})

        self.assertEqual(response.status_code, 403)
        event.refresh_from_db()
        self.assertEqual(event.title, "Imported")
        self.assertEqual(event.source_id, source.id)

    def test_external_id_stays_read_only_even_for_generic_source(self):
        source = IntegrationSource.objects.create(
            family=self.family,
            name="Legacy import",
            kind=IntegrationSource.Kind.GENERIC,
        )
        event = FamilyEvent.objects.create(
            family=self.family,
            source=source,
            type="calendar.event",
            title="Imported",
            external_id="uid-123",
        )

        self.assertTrue(_is_externally_managed_event(event))
        response = self._patch(event, {"title": "Should fail"})

        self.assertEqual(response.status_code, 403)
