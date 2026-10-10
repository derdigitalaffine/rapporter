import io
import tempfile
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from PIL import Image
from rest_framework.test import APIClient

from .family_master_models import FamilyMasterData
from .models import Family, Membership


class FamilyMasterDataTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user(username="family-owner", password="test-pass-123")
        self.adult = User.objects.create_user(username="family-adult", password="test-pass-123")
        self.outsider = User.objects.create_user(username="family-outsider", password="test-pass-123")
        self.family = Family.objects.create(name="Musterfamilie", slug="master-data-family")
        Membership.objects.create(family=self.family, user=self.owner, role=Membership.Role.OWNER, display_name="Alex")
        Membership.objects.create(family=self.family, user=self.adult, role=Membership.Role.ADULT, display_name="Sam")
        self.client = APIClient(); self.client.force_authenticate(self.owner)
        self.media = tempfile.TemporaryDirectory()
        self.override = override_settings(MEDIA_ROOT=self.media.name)
        self.override.enable()

    def tearDown(self):
        self.override.disable()
        self.media.cleanup()

    def _image(self):
        image = Image.new("RGB", (640, 360), (30, 110, 150))
        output = io.BytesIO(); image.save(output, format="PNG")
        return SimpleUploadedFile("family-private.png", output.getvalue(), content_type="image/png")

    def test_owner_updates_name_and_address_without_changing_slug_or_requiring_unique_name(self):
        Family.objects.create(name="Gleicher Name", slug="another-family")
        response = self.client.patch(
            f"/api/family-settings/?family={self.family.id}",
            {
                "family": str(self.family.id),
                "name": "Gleicher Name",
                "address_street": "Musterstraße",
                "address_house_number": "12a",
                "address_postal_code": "67655",
                "address_city": "Kaiserslautern",
                "address_region": "Rheinland-Pfalz",
                "address_country_code": "de",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.family.refresh_from_db()
        self.assertEqual(self.family.name, "Gleicher Name")
        self.assertEqual(self.family.slug, "master-data-family")
        self.assertEqual(Family.objects.filter(name="Gleicher Name").count(), 2)
        self.assertEqual(response.data["address_country_code"], "DE")
        context = response.data["location_context"]
        self.assertEqual(context["source"], "family_address")
        self.assertEqual(context["address"]["city"], "Kaiserslautern")
        self.assertTrue(context["ready_for_geocoding"])
        self.assertIsNone(context["coordinates"])

    def test_other_family_members_can_read_but_only_owner_can_mutate(self):
        FamilyMasterData.objects.create(family=self.family, address_city="Mainz", address_country_code="DE")
        adult = APIClient(); adult.force_authenticate(self.adult)
        read = adult.get(f"/api/family-settings/?family={self.family.id}")
        self.assertEqual(read.status_code, 200)
        self.assertFalse(read.data["can_edit"])
        self.assertEqual(read.data["address_city"], "Mainz")
        denied = adult.patch(f"/api/family-settings/?family={self.family.id}", {"name": "Nicht erlaubt"}, format="json")
        self.assertEqual(denied.status_code, 403)
        self.family.refresh_from_db()
        self.assertEqual(self.family.name, "Musterfamilie")

    def test_family_image_is_private_and_owner_managed(self):
        upload = self.client.post(
            f"/api/family-settings/image/?family={self.family.id}",
            {"image": self._image()},
            format="multipart",
        )
        self.assertEqual(upload.status_code, 200, upload.data)
        self.assertTrue(upload.data["image_url"])
        master = FamilyMasterData.objects.get(family=self.family)
        path = Path(self.media.name) / "private-images" / f"{master.image_key}.webp"
        self.assertTrue(path.is_file())
        with Image.open(path) as saved:
            self.assertEqual(saved.format, "WEBP")
            self.assertFalse(saved.getexif())

        adult = APIClient(); adult.force_authenticate(self.adult)
        allowed = adult.get(upload.data["image_url"])
        self.assertEqual(allowed.status_code, 200)
        denied_change = adult.delete(f"/api/family-settings/image/?family={self.family.id}")
        self.assertEqual(denied_change.status_code, 403)

        outsider = APIClient(); outsider.force_authenticate(self.outsider)
        blocked = outsider.get(upload.data["image_url"])
        self.assertEqual(blocked.status_code, 404)

        removed = self.client.delete(f"/api/family-settings/image/?family={self.family.id}")
        self.assertEqual(removed.status_code, 200)
        self.assertEqual(removed.data["image_url"], "")
        master.refresh_from_db()
        self.assertEqual(master.image_key, "")
        self.assertFalse(path.exists())

    def test_invalid_family_image_is_rejected(self):
        fake = SimpleUploadedFile("fake.png", b"not an image", content_type="image/png")
        response = self.client.post(f"/api/family-settings/image/?family={self.family.id}", {"image": fake}, format="multipart")
        self.assertEqual(response.status_code, 400)

    def test_outsider_cannot_read_family_master_data(self):
        outsider = APIClient(); outsider.force_authenticate(self.outsider)
        response = outsider.get(f"/api/family-settings/?family={self.family.id}")
        self.assertEqual(response.status_code, 403)
