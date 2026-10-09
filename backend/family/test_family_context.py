from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from .models import Family, Membership, ShoppingItem, ShoppingList, Task, TaskList


class DashboardFamilyContextTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="multi-family", password="test-pass-123")
        self.other_user = User.objects.create_user(username="outsider", password="test-pass-123")
        self.family_a = Family.objects.create(name="Family A", slug="family-a")
        self.family_b = Family.objects.create(name="Family B", slug="family-b")
        self.private_family = Family.objects.create(name="Private", slug="private-family")
        Membership.objects.create(family=self.family_a, user=self.user, role=Membership.Role.OWNER)
        Membership.objects.create(family=self.family_b, user=self.user, role=Membership.Role.ADULT)
        Membership.objects.create(family=self.private_family, user=self.other_user, role=Membership.Role.OWNER)

        list_a = TaskList.objects.create(family=self.family_a, name="A tasks")
        list_b = TaskList.objects.create(family=self.family_b, name="B tasks")
        Task.objects.create(family=self.family_a, task_list=list_a, title="Only A", created_by=self.user)
        Task.objects.create(family=self.family_b, task_list=list_b, title="Only B", created_by=self.user)
        shop_a = ShoppingList.objects.create(family=self.family_a, name="A shop")
        shop_b = ShoppingList.objects.create(family=self.family_b, name="B shop")
        ShoppingItem.objects.create(shopping_list=shop_a, name="Milk A", added_by=self.user)
        ShoppingItem.objects.create(shopping_list=shop_b, name="Milk B", added_by=self.user)

        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_dashboard_returns_only_requested_family(self):
        response = self.client.get(f"/api/dashboard/?family={self.family_b.id}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["family"], str(self.family_b.id))
        self.assertEqual([task["title"] for task in response.data["tasks"]], ["Only B"])
        self.assertEqual([row["name"] for row in response.data["shopping_lists"]], ["B shop"])

    def test_dashboard_rejects_family_without_membership(self):
        response = self.client.get(f"/api/dashboard/?family={self.private_family.id}")
        self.assertEqual(response.status_code, 403)
