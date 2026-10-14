from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from .models import Family, Membership, ShoppingItem, ShoppingList


class ShoppingTemplatePrivacyTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user(username="template-owner", password="x")
        self.recipient = User.objects.create_user(username="template-recipient", password="x")
        self.family = Family.objects.create(name="Template Family", slug="template-family")
        self.owner_member = Membership.objects.create(
            family=self.family,
            user=self.owner,
            role=Membership.Role.OWNER,
            display_name="Owner",
        )
        self.recipient_member = Membership.objects.create(
            family=self.family,
            user=self.recipient,
            role=Membership.Role.TEEN,
            display_name="Recipient",
        )
        self.client = APIClient()
        self.client.force_authenticate(self.owner)

    def test_family_template_never_copies_items_hidden_from_any_user(self):
        shopping = ShoppingList.objects.create(family=self.family, name="Family shopping")
        visible = ShoppingItem.objects.create(
            shopping_list=shopping,
            name="Milk",
            added_by=self.owner,
        )
        hidden_gift = ShoppingItem.objects.create(
            shopping_list=shopping,
            name="Birthday surprise",
            added_by=self.owner,
            hidden_from_user=self.recipient,
        )

        response = self.client.post(
            "/api/shopping-templates/from-list/",
            {
                "shopping_list": str(shopping.id),
                "name": "Safe template",
                "item_ids": [str(visible.id), str(hidden_gift.id)],
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual([row["name"] for row in response.data["items"]], ["Milk"])

    def test_template_created_list_applies_private_audience_atomically(self):
        template_response = self.client.post(
            "/api/shopping-templates/",
            {
                "family": str(self.family.id),
                "name": "Private errands",
                "items": [{"name": "Secret gift", "position": 0}],
            },
            format="json",
        )
        self.assertEqual(template_response.status_code, 201)

        create_response = self.client.post(
            f"/api/shopping-templates/{template_response.data['id']}/create-list/",
            {
                "visibility": "private",
                "responsible_members": [str(self.owner_member.id)],
            },
            format="json",
        )

        self.assertEqual(create_response.status_code, 201)
        self.assertEqual(create_response.data["access"]["visibility"], "private")
        list_id = create_response.data["id"]

        recipient_client = APIClient()
        recipient_client.force_authenticate(self.recipient)
        self.assertEqual(recipient_client.get(f"/api/shopping-lists/{list_id}/").status_code, 404)
