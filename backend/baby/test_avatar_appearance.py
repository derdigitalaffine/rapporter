import io
import tempfile
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from PIL import Image
from rest_framework.test import APIClient

from family.models import Family, Membership, UserProfile
from .models import BabyProfile, ManagedChildGuardian


class ManagedChildAvatarAppearanceTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user(username="avatar-owner", password="test-pass-123")
        self.guardian = User.objects.create_user(username="avatar-guardian", password="test-pass-123")
        self.adult = User.objects.create_user(username="avatar-adult", password="test-pass-123")
        self.child = User.objects.create_user(username="avatar-child", password="test-pass-123")
        self.family = Family.objects.create(name="Child Avatar Family", slug="child-avatar-family")
        self.owner_membership = Membership.objects.create(family=self.family, user=self.owner, role=Membership.Role.OWNER)
        self.guardian_membership = Membership.objects.create(family=self.family, user=self.guardian, role=Membership.Role.ADULT)
        self.adult_membership = Membership.objects.create(family=self.family, user=self.adult, role=Membership.Role.ADULT)
        self.child_membership = Membership.objects.create(family=self.family, user=self.child, role=Membership.Role.CHILD, display_name="Lina Sommer")
        UserProfile.objects.create(user=self.child)
        self.baby = BabyProfile.objects.create(
            family=self.family,
            membership=self.child_membership,
            display_name="Lina Sommer",
            birth_date="2018-04-03",
        )
        ManagedChildGuardian.objects.create(
            baby=self.baby,
            membership=self.guardian_membership,
            can_manage_account=True,
        )
        self.media = tempfile.TemporaryDirectory()
        self.override = override_settings(MEDIA_ROOT=self.media.name)
        self.override.enable()
        self.endpoint = f"/api/baby/memberships/{self.child_membership.id}/avatar/"

    def tearDown(self):
        self.override.disable()
        self.media.cleanup()

    def _client(self, user):
        client = APIClient()
        client.force_authenticate(user)
        return client

    def _image(self, size=(720, 480)):
        image = Image.new("RGB", size, (70, 120, 160))
        buffer = io.BytesIO()
        image.save(buffer, format="JPEG")
        return SimpleUploadedFile("child.jpg", buffer.getvalue(), content_type="image/jpeg")

    def test_owner_guardian_and_child_can_edit_but_unrelated_adult_cannot(self):
        self.assertEqual(self._client(self.owner).get(self.endpoint).status_code, 200)
        self.assertEqual(self._client(self.guardian).get(self.endpoint).status_code, 200)
        self.assertEqual(self._client(self.child).get(self.endpoint).status_code, 200)
        self.assertEqual(self._client(self.adult).get(self.endpoint).status_code, 403)

    def test_guardian_can_choose_symbol_color_and_photo_source(self):
        client = self._client(self.guardian)
        configured = client.patch(
            self.endpoint,
            {"avatar_mode": "icon", "avatar_icon_key": "dragon", "avatar_color": "#123ABC"},
            format="json",
        )
        self.assertEqual(configured.status_code, 200, configured.data)
        uploaded = client.post(
            self.endpoint,
            {"avatar": self._image((512, 512)), "avatar_source": self._image((1200, 800))},
            format="multipart",
        )
        self.assertEqual(uploaded.status_code, 200, uploaded.data)
        self.assertEqual(uploaded.data["avatar_mode"], "photo")
        profile = UserProfile.objects.get(user=self.child)
        self.assertEqual(profile.avatar_icon_key, "dragon")
        source_path = Path(self.media.name) / "avatars" / f"{profile.avatar_key}-source.webp"
        self.assertTrue(source_path.exists())
        with Image.open(source_path) as source:
            self.assertEqual(source.size, (1200, 800))
        source = client.get(uploaded.data["avatar_edit_url"])
        self.assertEqual(source.status_code, 200)
        self.assertEqual(source["Content-Type"], "image/webp")

    def test_non_guardian_adult_cannot_upload_or_fetch_edit_source(self):
        guardian = self._client(self.guardian)
        uploaded = guardian.post(self.endpoint, {"avatar": self._image()}, format="multipart")
        self.assertEqual(uploaded.status_code, 200)
        adult = self._client(self.adult)
        denied_upload = adult.post(self.endpoint, {"avatar": self._image()}, format="multipart")
        self.assertEqual(denied_upload.status_code, 403)
        denied_source = adult.get(uploaded.data["avatar_edit_url"])
        self.assertEqual(denied_source.status_code, 403)

    def test_child_can_change_own_avatar_after_login_is_available(self):
        client = self._client(self.child)
        response = client.patch(
            self.endpoint,
            {"avatar_mode": "icon", "avatar_icon_key": "football", "avatar_color": "#A65353"},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["avatar_icon_key"], "football")

    def test_removing_photo_returns_to_previous_symbol(self):
        client = self._client(self.owner)
        self.assertEqual(client.patch(self.endpoint, {"avatar_mode": "icon", "avatar_icon_key": "rocket"}, format="json").status_code, 200)
        self.assertEqual(client.post(self.endpoint, {"avatar": self._image()}, format="multipart").status_code, 200)
        removed = client.delete(self.endpoint)
        self.assertEqual(removed.status_code, 200)
        self.assertEqual(removed.data["avatar_mode"], "icon")
        self.assertEqual(removed.data["avatar_icon_key"], "rocket")
