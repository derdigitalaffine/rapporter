import io
import tempfile
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from PIL import Image
from rest_framework.test import APIClient

from .avatar_appearance import AVATAR_COLOR_PALETTE
from .models import Family, Membership, UserProfile


class AvatarAppearanceTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="avatar-user", password="test-pass-123")
        self.family = Family.objects.create(name="Avatar Family", slug="avatar-family")
        self.membership = Membership.objects.create(
            family=self.family,
            user=self.user,
            role=Membership.Role.OWNER,
            display_name="Mia Sommer",
        )
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.media = tempfile.TemporaryDirectory()
        self.override = override_settings(MEDIA_ROOT=self.media.name)
        self.override.enable()

    def tearDown(self):
        self.override.disable()
        self.media.cleanup()

    def _image(self):
        image = Image.new("RGB", (600, 400), (90, 130, 170))
        buffer = io.BytesIO()
        image.save(buffer, format="JPEG")
        return SimpleUploadedFile("avatar.jpg", buffer.getvalue(), content_type="image/jpeg")

    def test_default_appearance_is_initials_with_deterministic_palette_color(self):
        response = self.client.get(f"/api/profile/?family={self.family.id}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["avatar_mode"], "initials")
        self.assertIn(response.data["avatar_color"], AVATAR_COLOR_PALETTE)
        self.assertGreaterEqual(len(response.data["avatar_icon_options"]), 50)

    def test_profile_can_switch_to_allowlisted_symbol_and_custom_color(self):
        response = self.client.patch(
            f"/api/profile/?family={self.family.id}",
            {
                "family": str(self.family.id),
                "avatar_mode": "icon",
                "avatar_icon_key": "rocket",
                "avatar_color": "#123ABC",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["avatar_mode"], "icon")
        self.assertEqual(response.data["avatar_icon_key"], "rocket")
        self.assertEqual(response.data["avatar_color"], "#123ABC")
        profile = UserProfile.objects.get(user=self.user)
        self.assertEqual(profile.avatar_icon_key, "rocket")

    def test_invalid_symbol_and_color_are_rejected(self):
        bad_icon = self.client.patch(
            f"/api/profile/?family={self.family.id}",
            {"family": str(self.family.id), "avatar_mode": "icon", "avatar_icon_key": "<svg>"},
            format="json",
        )
        self.assertEqual(bad_icon.status_code, 400)
        bad_color = self.client.patch(
            f"/api/profile/?family={self.family.id}",
            {"family": str(self.family.id), "avatar_color": "red; background:url(x)"},
            format="json",
        )
        self.assertEqual(bad_color.status_code, 400)

    def test_photo_delete_restores_previous_symbol_and_keeps_color(self):
        configured = self.client.patch(
            f"/api/profile/?family={self.family.id}",
            {
                "family": str(self.family.id),
                "avatar_mode": "icon",
                "avatar_icon_key": "rainbow",
                "avatar_color": "#6B5FA7",
            },
            format="json",
        )
        self.assertEqual(configured.status_code, 200)
        uploaded = self.client.post(
            f"/api/profile/avatar/?family={self.family.id}",
            {"avatar": self._image()},
            format="multipart",
        )
        self.assertEqual(uploaded.status_code, 200, uploaded.data)
        self.assertEqual(uploaded.data["avatar_mode"], "photo")
        profile = UserProfile.objects.get(user=self.user)
        old_key = profile.avatar_key
        self.assertEqual(profile.avatar_icon_key, "rainbow")
        self.assertTrue((Path(self.media.name) / "avatars" / f"{old_key}-source.webp").exists())
        removed = self.client.delete(f"/api/profile/avatar/?family={self.family.id}")
        self.assertEqual(removed.status_code, 200)
        self.assertEqual(removed.data["avatar_mode"], "icon")
        self.assertEqual(removed.data["avatar_icon_key"], "rainbow")
        self.assertEqual(removed.data["avatar_color"], "#6B5FA7")

    def test_avatar_and_calendar_colors_are_independent(self):
        response = self.client.patch(
            f"/api/profile/?family={self.family.id}",
            {
                "family": str(self.family.id),
                "avatar_color": "#123ABC",
                "calendar_color": "#2f6f73",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["avatar_color"], "#123ABC")
        self.assertEqual(response.data["calendar_color"].lower(), "#2f6f73")
