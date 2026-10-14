import io
import tempfile
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from PIL import Image
from rest_framework.test import APIClient

from family.models import Family, Membership, UserProfile


class ManagedChildAppearanceTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user(username='owner', password='test-pass-123')
        self.adult = User.objects.create_user(username='adult', password='test-pass-123')
        self.teen = User.objects.create_user(username='teen', password='test-pass-123')
        self.child = User.objects.create_user(username='child-managed')
        self.other_adult = User.objects.create_user(username='other-adult', password='test-pass-123')
        self.family = Family.objects.create(name='Family', slug='family')
        Membership.objects.create(family=self.family, user=self.owner, role=Membership.Role.OWNER, display_name='Owner')
        Membership.objects.create(family=self.family, user=self.adult, role=Membership.Role.ADULT, display_name='Adult')
        Membership.objects.create(family=self.family, user=self.teen, role=Membership.Role.TEEN, display_name='Teen')
        self.child_membership = Membership.objects.create(family=self.family, user=self.child, role=Membership.Role.CHILD, display_name='Mia')
        self.other_adult_membership = Membership.objects.create(family=self.family, user=self.other_adult, role=Membership.Role.ADULT, display_name='Other')
        UserProfile.objects.create(user=self.child)
        self.client = APIClient()
        self.media = tempfile.TemporaryDirectory()
        self.override = override_settings(MEDIA_ROOT=self.media.name)
        self.override.enable()

    def tearDown(self):
        self.override.disable()
        self.media.cleanup()

    def _image(self):
        image = Image.new('RGB', (320, 240), (80, 120, 160))
        buffer = io.BytesIO()
        image.save(buffer, format='PNG')
        return SimpleUploadedFile('child.png', buffer.getvalue(), content_type='image/png')

    def _url(self, membership=None):
        membership = membership or self.child_membership
        return f'/api/baby/memberships/{membership.id}/avatar/'

    def test_owner_can_upload_and_remove_child_avatar(self):
        self.client.force_authenticate(self.owner)
        response = self.client.post(self._url(), {'avatar': self._image()}, format='multipart')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertTrue(response.data['avatar_url'])
        profile = UserProfile.objects.get(user=self.child)
        for size in (64, 128, 256):
            self.assertTrue((Path(self.media.name) / 'avatars' / f'{profile.avatar_key}-{size}.webp').is_file())

        response = self.client.delete(self._url())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['avatar_url'], '')
        profile.refresh_from_db()
        self.assertEqual(profile.avatar_key, '')

    def test_adult_can_manage_child_avatar_without_child_guardian_permission(self):
        self.client.force_authenticate(self.adult)
        response = self.client.post(self._url(), {'avatar': self._image()}, format='multipart')
        self.assertEqual(response.status_code, 200, response.data)

    def test_teen_cannot_manage_child_avatar(self):
        self.client.force_authenticate(self.teen)
        response = self.client.post(self._url(), {'avatar': self._image()}, format='multipart')
        self.assertEqual(response.status_code, 403)

    def test_manager_cannot_replace_another_adults_avatar(self):
        self.client.force_authenticate(self.owner)
        response = self.client.post(self._url(self.other_adult_membership), {'avatar': self._image()}, format='multipart')
        self.assertEqual(response.status_code, 403)