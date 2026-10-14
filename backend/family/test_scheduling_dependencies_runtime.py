from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from .models import Family, FamilyEvent, Membership
from .scheduling_dependencies import create_relative_dependency, refresh_dependency
from .scheduling_models import SchedulingDependency, SchedulingMaterialization
from .scheduling_relative import apply_relative_rule


User = get_user_model()
BERLIN = ZoneInfo("Europe/Berlin")


class RelativeSchedulingRuntimeTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="relative-owner", password="x")
        self.family = Family.objects.create(name="Relative", slug="relative", timezone="Europe/Berlin")
        Membership.objects.create(family=self.family, user=self.user, role=Membership.Role.OWNER)
        start = timezone.now().astimezone(BERLIN) + timedelta(days=14)
        start = start.replace(hour=10, minute=0, second=0, microsecond=0)
        self.event = FamilyEvent.objects.create(
            family=self.family,
            type="calendar.event",
            title="Restmüll",
            starts_at=start,
            ends_at=start + timedelta(hours=1),
            payload={"provider": "FamilyOS", "location": "Hof"},
        )

    def test_wall_clock_offset_and_weekday_relationship(self):
        anchor = datetime(2026, 11, 12, 10, 0, tzinfo=BERLIN)  # Thursday
        value = apply_relative_rule(
            anchor,
            {
                "direction": "before",
                "offset": {"value": 0, "unit": "days"},
                "weekday": {"day": "MO", "mode": "before"},
                "time": "18:00",
            },
            "Europe/Berlin",
        )
        self.assertEqual(value.isoformat(), "2026-11-09T18:00:00+01:00")

    def test_create_dependency_materializes_event_once_and_reuses_it(self):
        dependency = create_relative_dependency(
            family=self.family,
            anchor_type="calendar.event",
            anchor_id=self.event.id,
            output_type=SchedulingDependency.OutputType.EVENT,
            relative_rule={"direction": "before", "offset": {"value": 3, "unit": "days"}, "time": "18:00"},
            output_blueprint={"title": "Tonnen rausstellen", "duration_minutes": 15},
            inheritance={"location": True},
            actor=self.user,
        )
        materialization = dependency.materializations.get()
        derived = FamilyEvent.objects.get(id=materialization.output_id)
        self.assertEqual(derived.title, "Tonnen rausstellen")
        self.assertEqual(derived.payload["location"], "Hof")
        self.assertEqual(derived.starts_at.astimezone(BERLIN).hour, 18)
        self.assertEqual(FamilyEvent.objects.filter(payload__scheduling_origin__dependency_id=str(dependency.id)).count(), 1)

        refresh_dependency(dependency)
        self.assertEqual(dependency.materializations.count(), 1)
        self.assertEqual(FamilyEvent.objects.filter(payload__scheduling_origin__dependency_id=str(dependency.id)).count(), 1)

    def test_anchor_change_moves_derived_event(self):
        dependency = create_relative_dependency(
            family=self.family,
            anchor_type="calendar.event",
            anchor_id=self.event.id,
            output_type=SchedulingDependency.OutputType.EVENT,
            relative_rule={"direction": "before", "offset": {"value": 1, "unit": "days"}},
            output_blueprint={"title": "Vorbereitung"},
            actor=self.user,
        )
        row = dependency.materializations.get()
        derived = FamilyEvent.objects.get(id=row.output_id)
        old_start = derived.starts_at
        self.event.starts_at += timedelta(days=2)
        self.event.ends_at += timedelta(days=2)
        self.event.save()
        refresh_dependency(dependency)
        derived.refresh_from_db()
        self.assertEqual(derived.starts_at, old_start + timedelta(days=2))


class SchedulingDependencyApiTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="dependency-api", password="x")
        self.family = Family.objects.create(name="Dependency API", slug="dependency-api", timezone="Europe/Berlin")
        Membership.objects.create(family=self.family, user=self.user, role=Membership.Role.ADULT)
        self.event = FamilyEvent.objects.create(
            family=self.family,
            type="calendar.event",
            title="Abholung",
            starts_at=timezone.now() + timedelta(days=10),
            ends_at=timezone.now() + timedelta(days=10, hours=1),
            payload={"provider": "FamilyOS"},
        )
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.base = f"?family={self.family.id}"

    def test_preview_create_and_list_dependency(self):
        payload = {
            "anchor_type": "calendar.event",
            "anchor_id": str(self.event.id),
            "output_type": "calendar.event",
            "output_blueprint": {"title": "Vorbereitung", "duration_minutes": 30},
            "relative_rule": {"direction": "before", "offset": {"value": 2, "unit": "days"}, "time": "18:00"},
            "inheritance": {},
        }
        preview = self.client.post(f"/api/scheduling/dependencies/preview/{self.base}", payload, format="json")
        self.assertEqual(preview.status_code, 200, preview.data)
        self.assertEqual(len(preview.data["occurrences"]), 1)
        self.assertIn("2 Tage vorher", preview.data["summary"])

        created = self.client.post(f"/api/scheduling/dependencies/{self.base}", payload, format="json")
        self.assertEqual(created.status_code, 201, created.data)
        self.assertEqual(created.data["output_blueprint"]["title"], "Vorbereitung")
        self.assertEqual(len(created.data["materializations"]), 1)

        listed = self.client.get(f"/api/scheduling/dependencies/{self.base}&anchor_type=calendar.event&anchor_id={self.event.id}")
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(len(listed.data["dependencies"]), 1)

    def test_cross_family_anchor_is_rejected(self):
        other = Family.objects.create(name="Other", slug="relative-other")
        other_event = FamilyEvent.objects.create(family=other, type="calendar.event", title="Other")
        response = self.client.post(
            f"/api/scheduling/dependencies/{self.base}",
            {
                "anchor_type": "calendar.event",
                "anchor_id": str(other_event.id),
                "output_type": "calendar.event",
                "relative_rule": {"direction": "before", "offset": {"value": 1, "unit": "days"}},
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)
