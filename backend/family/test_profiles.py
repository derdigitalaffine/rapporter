import io
import tempfile
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from PIL import Image
from rest_framework.test import APIClient

from .models import Family, Membership, UserProfile


class ProfileTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user(username="profile-owner", password="test-pass-123", email="owner@example.com")
        self.member = User.objects.create_user(username="profile-member", password="test-pass-123")
        self.outsider = User.objects.create_user(username="profile-outsider", password="test-pass-123")
        self.family = Family.objects.create(name="Profile Family", slug="profile-family")
        self.owner_membership = Membership.objects.create(family=self.family, user=self.owner, role=Membership.Role.OWNER, display_name="Alex")
        self.member_membership = Membership.objects.create(family=self.family, user=self.member, role=Membership.Role.ADULT, display_name="Mia")
        self.client = APIClient()
        self.client.force_authenticate(self.owner)
        self.media = tempfile.TemporaryDirectory()
        self.override = override_settings(MEDIA_ROOT=self.media.name)
        self.override.enable()

    def tearDown(self):
        self.override.disable()
        self.media.cleanup()

    def _image(self, fmt="PNG", name="original-name.png", size=(480, 320), exif=False):
        image = Image.new("RGB", size, (120, 80, 40))
        buffer = io.BytesIO()
        kwargs = {}
        if exif and fmt == "JPEG":
            metadata = Image.Exif()
            metadata[0x010E] = "private metadata"
            kwargs["exif"] = metadata
        image.save(buffer, format=fmt, **kwargs)
        mime = {"PNG": "image/png", "JPEG": "image/jpeg", "WEBP": "image/webp"}[fmt]
        return SimpleUploadedFile(name, buffer.getvalue(), content_type=mime)

    def _family_memberships(self):
        response = self.client.get("/api/families/")
        self.assertEqual(response.status_code, 200)
        families = response.data.get("results", response.data)
        return families[0]["memberships"]

    def test_user_can_read_and_update_own_profile(self):
        response = self.client.patch(
            f"/api/profile/?family={self.family.id}",
            {"family": str(self.family.id), "display_name": "Alex Neu", "birth_month": 2, "birth_day": 29, "birth_year": 2000, "birthday_visibility": "full_date"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["display_name"], "Alex Neu")
        self.assertEqual(response.data["birth_day"], 29)
        self.assertEqual(response.data["birthday_visibility"], "full_date")
        profile = UserProfile.objects.get(user=self.owner)
        self.assertEqual((profile.birth_year, profile.birth_month, profile.birth_day), (2000, 2, 29))
        self.owner_membership.refresh_from_db()
        self.assertEqual(self.owner_membership.display_name, "Alex Neu")

    def test_invalid_birthday_is_rejected(self):
        response = self.client.patch(
            f"/api/profile/?family={self.family.id}",
            {"family": str(self.family.id), "birth_month": 2, "birth_day": 30, "birth_year": 2000},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(UserProfile.objects.filter(user=self.owner, birth_month__isnull=False).exists())

    def test_invalid_visibility_does_not_partially_store_birthday(self):
        response = self.client.patch(
            f"/api/profile/?family={self.family.id}",
            {"family": str(self.family.id), "birth_month": 3, "birth_day": 12, "birth_year": 1990, "birthday_visibility": "everyone"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        profile = UserProfile.objects.get(user=self.owner)
        self.assertIsNone(profile.birth_month)
        self.owner_membership.refresh_from_db()
        self.assertEqual(self.owner_membership.birthday_visibility, Membership.BirthdayVisibility.DAY_MONTH)

    def test_membership_serialization_respects_birthday_visibility(self):
        UserProfile.objects.create(user=self.member, birth_month=3, birth_day=12, birth_year=2010)
        self.member_membership.birthday_visibility = Membership.BirthdayVisibility.HIDDEN
        self.member_membership.save(update_fields=["birthday_visibility"])
        row = next(x for x in self._family_memberships() if x["user"] == self.member.id)
        self.assertIsNone(row["birth_month"])
        self.assertIsNone(row["birth_year"])

        self.member_membership.birthday_visibility = Membership.BirthdayVisibility.DAY_MONTH
        self.member_membership.save(update_fields=["birthday_visibility"])
        row = next(x for x in self._family_memberships() if x["user"] == self.member.id)
        self.assertEqual((row["birth_month"], row["birth_day"]), (3, 12))
        self.assertIsNone(row["birth_year"])

        self.member_membership.birthday_visibility = Membership.BirthdayVisibility.FULL_DATE
        self.member_membership.save(update_fields=["birthday_visibility"])
        row = next(x for x in self._family_memberships() if x["user"] == self.member.id)
        self.assertEqual(row["birth_year"], 2010)

    def test_other_user_profile_cannot_be_patched(self):
        UserProfile.objects.create(user=self.member, birth_month=4, birth_day=5, birth_year=2001)
        response = self.client.patch(
            f"/api/memberships/{self.member_membership.id}/",
            {"birthday_visibility": "hidden"},
            format="json",
        )
        self.assertEqual(response.status_code, 403)
        self.member_membership.refresh_from_db()
        self.assertEqual(self.member_membership.birthday_visibility, Membership.BirthdayVisibility.DAY_MONTH)
        profile = UserProfile.objects.get(user=self.member)
        self.assertEqual(profile.birth_year, 2001)

    def test_png_jpeg_and_webp_uploads_are_reencoded_to_private_webp_renditions(self):
        for fmt in ("PNG", "JPEG", "WEBP"):
            response = self.client.post(
                f"/api/profile/avatar/?family={self.family.id}",
                {"avatar": self._image(fmt, name=f"secret-{fmt.lower()}.bin", exif=fmt == "JPEG")},
                format="multipart",
            )
            self.assertEqual(response.status_code, 200, response.data)
            profile = UserProfile.objects.get(user=self.owner)
            self.assertNotIn("secret-", profile.avatar_key)
            for size in (64, 128, 256):
                path = Path(self.media.name) / "avatars" / f"{profile.avatar_key}-{size}.webp"
                self.assertTrue(path.is_file())
                with Image.open(path) as saved:
                    self.assertEqual(saved.format, "WEBP")
                    self.assertEqual(saved.size, (size, size))
                    self.assertFalse(saved.getexif())

    def test_fake_image_and_oversize_upload_are_rejected(self):
        fake = SimpleUploadedFile("avatar.png", b"not actually a png", content_type="image/png")
        response = self.client.post("/api/profile/avatar/", {"avatar": fake}, format="multipart")
        self.assertEqual(response.status_code, 400)
        huge = SimpleUploadedFile("huge.jpg", b"x" * (10 * 1024 * 1024 + 1), content_type="image/jpeg")
        response = self.client.post("/api/profile/avatar/", {"avatar": huge}, format="multipart")
        self.assertEqual(response.status_code, 400)

    def test_avatar_is_only_available_to_self_or_shared_family(self):
        response = self.client.post("/api/profile/avatar/", {"avatar": self._image()}, format="multipart")
        self.assertEqual(response.status_code, 200)
        url = response.data["avatar_url"]
        shared = APIClient(); shared.force_authenticate(self.member)
        allowed = shared.get(url)
        self.assertEqual(allowed.status_code, 200)
        outsider = APIClient(); outsider.force_authenticate(self.outsider)
        blocked = outsider.get(url)
        self.assertEqual(blocked.status_code, 404)

    def test_avatar_delete_restores_initials_fallback_contract(self):
        self.client.post("/api/profile/avatar/", {"avatar": self._image()}, format="multipart")
        response = self.client.delete(f"/api/profile/avatar/?family={self.family.id}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["avatar_url"], "")
        self.assertEqual(UserProfile.objects.get(user=self.owner).avatar_key, "")
