import io
import tempfile
from datetime import date

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from PIL import Image
from rest_framework.test import APIClient

from .models import Family, FamilyEvent, Membership
from .private_images import image_path
from .travel_models import Trip, TripPhoto


class TravelTests(TestCase):
    def setUp(self):
        self.media = tempfile.TemporaryDirectory()
        self.addCleanup(self.media.cleanup)
        override = override_settings(MEDIA_ROOT=self.media.name)
        override.enable()
        self.addCleanup(override.disable)
        User = get_user_model()
        self.owner = User.objects.create_user("travel-owner")
        self.adult = User.objects.create_user("travel-adult")
        self.teen = User.objects.create_user("travel-teen")
        self.child = User.objects.create_user("travel-child")
        self.guest = User.objects.create_user("travel-guest")
        self.outsider = User.objects.create_user("travel-outsider")
        self.family = Family.objects.create(name="Home", slug="travel-home")
        self.other = Family.objects.create(name="Other", slug="travel-other")
        for user, role in [
            (self.owner, "owner"),
            (self.adult, "adult"),
            (self.teen, "teen"),
            (self.child, "child"),
            (self.guest, "guest"),
        ]:
            Membership.objects.create(family=self.family, user=user, role=role, display_name=user.username)
        Membership.objects.create(family=self.other, user=self.outsider, role="owner")
        self.client = APIClient()
        self.client.force_authenticate(self.owner)

    def payload(self, **extra):
        data = {
            "family": str(self.family.id),
            "title": "Sommerurlaub",
            "destination": "Nordsee",
            "starts_on": "2027-07-10",
            "ends_on": "2027-07-17",
            "notes": "Gemeinsam ans Meer",
        }
        data.update(extra)
        return data

    def image(self):
        output = io.BytesIO()
        image = Image.new("RGB", (2200, 1200), "blue")
        exif = Image.Exif()
        exif[270] = "private note"
        image.save(output, "JPEG", exif=exif)
        return SimpleUploadedFile("holiday.jpg", output.getvalue(), content_type="image/jpeg")

    def create_trip(self):
        response = self.client.post("/api/trips/", self.payload(), format="json")
        self.assertEqual(response.status_code, 201, response.data)
        return response.data

    def test_crud_roles_dates_and_calendar_sync(self):
        created = self.create_trip()
        trip = Trip.objects.select_related("calendar_event").get(pk=created["id"])
        self.assertEqual(trip.calendar_event.type, "travel.trip")
        self.assertEqual(trip.calendar_event.payload["trip_id"], str(trip.id))
        self.assertEqual(trip.calendar_event.payload["civil_start"], "2027-07-10")
        self.assertEqual(trip.calendar_event.payload["civil_end"], "2027-07-17")
        self.assertEqual(trip.calendar_event.starts_at.date(), date(2027, 7, 10))
        self.assertEqual(trip.calendar_event.ends_at.date(), date(2027, 7, 18))

        response = self.client.patch(
            f"/api/trips/{trip.id}/",
            {"title": "Meerurlaub", "ends_on": "2027-07-20"},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        trip.refresh_from_db()
        trip.calendar_event.refresh_from_db()
        self.assertEqual(trip.calendar_event.title, "Meerurlaub")
        self.assertEqual(trip.calendar_event.payload["civil_end"], "2027-07-20")

        self.client.force_authenticate(self.teen)
        self.assertEqual(self.client.post("/api/trips/", self.payload(title="No"), format="json").status_code, 403)
        self.assertEqual(self.client.patch(f"/api/trips/{trip.id}/", {"title": "No"}, format="json").status_code, 403)

        self.client.force_authenticate(self.adult)
        self.assertEqual(self.client.patch(f"/api/trips/{trip.id}/", {"title": "Adult edit"}, format="json").status_code, 200)

        self.client.force_authenticate(self.owner)
        invalid = self.client.post("/api/trips/", self.payload(starts_on="2027-08-10", ends_on="2027-08-01"), format="json")
        self.assertEqual(invalid.status_code, 400)

    def test_family_isolation_and_calendar_read_only(self):
        created = self.create_trip()
        event_id = created["calendar_event_id"]
        self.assertEqual(self.client.patch(f"/api/events/{event_id}/", {"title": "Drift"}, format="json").status_code, 403)
        self.assertEqual(self.client.delete(f"/api/events/{event_id}/").status_code, 403)

        self.client.force_authenticate(self.outsider)
        self.assertEqual(self.client.get("/api/trips/").data["results"], [])
        self.assertEqual(self.client.get(f"/api/trips/{created['id']}/").status_code, 404)

    def test_private_photo_upload_permissions_cleanup(self):
        created = self.create_trip()
        trip_id = created["id"]

        self.client.force_authenticate(self.child)
        response = self.client.post(
            f"/api/trips/{trip_id}/photos/",
            {"images": [self.image()], "caption": "Strand"},
            format="multipart",
        )
        self.assertEqual(response.status_code, 201, response.data)
        photo = TripPhoto.objects.get(trip_id=trip_id)
        path = image_path(photo.key)
        self.assertTrue(path.exists())
        with Image.open(path) as decoded:
            self.assertEqual(decoded.format, "WEBP")
            self.assertLessEqual(max(decoded.size), 1600)
            self.assertFalse(decoded.getexif())
        photo_url = response.data["photos"][0]["url"]
        response_file = self.client.get(photo_url)
        self.assertEqual(response_file.status_code, 200)
        self.assertEqual(response_file["Cache-Control"], "private, no-store")

        self.client.force_authenticate(self.guest)
        self.assertEqual(
            self.client.post(f"/api/trips/{trip_id}/photos/", {"images": [self.image()]}, format="multipart").status_code,
            403,
        )
        self.client.force_authenticate(self.outsider)
        self.assertEqual(self.client.get(photo_url).status_code, 404)

        self.client.force_authenticate(self.child)
        with self.captureOnCommitCallbacks(execute=True):
            self.assertEqual(self.client.delete(photo_url).status_code, 204)
        self.assertFalse(path.exists())

    def test_delete_trip_removes_event_and_media(self):
        created = self.create_trip()
        trip_id = created["id"]
        event_id = created["calendar_event_id"]
        self.client.post(f"/api/trips/{trip_id}/photos/", {"images": [self.image()]}, format="multipart")
        photo = TripPhoto.objects.get(trip_id=trip_id)
        path = image_path(photo.key)
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.delete(f"/api/trips/{trip_id}/")
        self.assertEqual(response.status_code, 204)
        self.assertFalse(Trip.objects.filter(id=trip_id).exists())
        self.assertFalse(FamilyEvent.objects.filter(id=event_id).exists())
        self.assertFalse(path.exists())
