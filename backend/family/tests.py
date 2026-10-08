from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient
from .models import Family, Membership, Task, InboxItem, ShoppingItem


class FamilyApiTests(TestCase):
    def setUp(self):
        User=get_user_model()
        self.alice=User.objects.create_user(username="alice",password="test-pass-123")
        self.bob=User.objects.create_user(username="bob",password="test-pass-123")
        self.family=Family.objects.create(name="Alice Family",slug="alice-family")
        self.other=Family.objects.create(name="Bob Family",slug="bob-family")
        Membership.objects.create(family=self.family,user=self.alice,role=Membership.Role.OWNER)
        Membership.objects.create(family=self.other,user=self.bob,role=Membership.Role.OWNER)
        self.client=APIClient();self.client.force_authenticate(self.alice)

    def test_tasks_are_isolated_by_family(self):
        own=Task.objects.create(family=self.family,title="Own",created_by=self.alice)
        Task.objects.create(family=self.other,title="Secret",created_by=self.bob)
        response=self.client.get("/api/tasks/")
        self.assertEqual(response.status_code,200)
        ids={str(item["id"]) for item in response.data.get("results",response.data)}
        self.assertEqual(ids,{str(own.id)})

    def test_cannot_create_task_for_other_family(self):
        response=self.client.post("/api/tasks/",{"family":str(self.other.id),"title":"Nope"},format="json")
        self.assertEqual(response.status_code,403)
        self.assertFalse(Task.objects.filter(family=self.other,title="Nope").exists())

    def test_inbox_item_can_be_converted_to_task(self):
        item=InboxItem.objects.create(family=self.family,title="Milch holen",body="Bitte heute",source="share")
        response=self.client.post(f"/api/inbox/{item.id}/to_task/",{},format="json")
        self.assertEqual(response.status_code,201)
        self.assertTrue(Task.objects.filter(family=self.family,title="Milch holen",source="inbox:share").exists())
        item.refresh_from_db();self.assertEqual(item.status,"processed")

    def test_inbox_item_can_be_converted_to_shopping(self):
        item=InboxItem.objects.create(family=self.family,title="Äpfel",source="share")
        response=self.client.post(f"/api/inbox/{item.id}/to_shopping/",{},format="json")
        self.assertEqual(response.status_code,201)
        self.assertTrue(ShoppingItem.objects.filter(shopping_list__family=self.family,name="Äpfel").exists())
        item.refresh_from_db();self.assertEqual(item.status,"processed")
