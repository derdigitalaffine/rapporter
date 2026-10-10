from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from .models import Family, Membership


class ShoppingTemplateTenantImmutabilityTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="shopping-multi-family", password="test-pass-123")
        self.first = Family.objects.create(name="First Family", slug="shopping-first")
        self.second = Family.objects.create(name="Second Family", slug="shopping-second")
        Membership.objects.create(family=self.first, user=self.user, role=Membership.Role.OWNER)
        Membership.objects.create(family=self.second, user=self.user, role=Membership.Role.OWNER)
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_store_and_template_family_are_immutable_after_creation(self):
        store = self.client.post(
            "/api/shopping-stores/",
            {"family": str(self.first.id), "name": "Store"},
            format="json",
        )
        self.assertEqual(store.status_code, 201, store.data)
        moved_store = self.client.patch(
            f"/api/shopping-stores/{store.data['id']}/",
            {"family": str(self.second.id)},
            format="json",
        )
        self.assertEqual(moved_store.status_code, 400, moved_store.data)

        template = self.client.post(
            "/api/shopping-templates/",
            {"family": str(self.first.id), "name": "Template", "items": [{"name": "Milk"}]},
            format="json",
        )
        self.assertEqual(template.status_code, 201, template.data)
        moved_template = self.client.patch(
            f"/api/shopping-templates/{template.data['id']}/",
            {"family": str(self.second.id)},
            format="json",
        )
        self.assertEqual(moved_template.status_code, 400, moved_template.data)
