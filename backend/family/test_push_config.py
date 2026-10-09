import os
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from .models import Family, Membership
from .push import public_key, push_configured


class PushConfigurationTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="push-config-user", password="test-pass-123")
        self.family = Family.objects.create(name="Push Config Family", slug="push-config-family")
        Membership.objects.create(family=self.family, user=self.user, role=Membership.Role.OWNER)
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    @patch.dict(os.environ, {"VAPID_PUBLIC_KEY": "public-test-key", "VAPID_PRIVATE_KEY": "private-test-key"}, clear=False)
    def test_configured_push_exposes_only_public_key(self):
        self.assertTrue(push_configured())
        self.assertEqual(public_key(), "public-test-key")
        response = self.client.get("/api/push/config/")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["configured"])
        self.assertEqual(response.data["public_key"], "public-test-key")
        self.assertNotIn("private_key", response.data)
        self.assertNotIn("private-test-key", str(response.data))

    @patch.dict(os.environ, {"VAPID_PUBLIC_KEY": "", "VAPID_PRIVATE_KEY": ""}, clear=False)
    def test_missing_pair_is_reported_without_key_material(self):
        self.assertFalse(push_configured())
        response = self.client.get("/api/push/config/")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["configured"])
        self.assertEqual(response.data["public_key"], "")
        self.assertNotIn("private_key", response.data)

    @patch.dict(os.environ, {"VAPID_PUBLIC_KEY": "public-only", "VAPID_PRIVATE_KEY": ""}, clear=False)
    def test_partial_pair_is_not_considered_configured(self):
        self.assertFalse(push_configured())
