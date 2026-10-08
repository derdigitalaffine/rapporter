from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from .models import Family, Membership, Task, InboxItem, ShoppingItem, IntegrationSource


class FamilyApiTests(TestCase):
    def setUp(self):
        User=get_user_model()
        self.alice=User.objects.create_user(username="alice",password="test-pass-123")
        self.bob=User.objects.create_user(username="bob",password="test-pass-123")
        self.teen=User.objects.create_user(username="teen",password="test-pass-123")
        self.family=Family.objects.create(name="Alice Family",slug="alice-family")
        self.other=Family.objects.create(name="Bob Family",slug="bob-family")
        Membership.objects.create(family=self.family,user=self.alice,role=Membership.Role.OWNER)
        Membership.objects.create(family=self.family,user=self.teen,role=Membership.Role.TEEN)
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

    def test_integration_catalog_is_available_in_app_api(self):
        response=self.client.get("/api/integrations/catalog/")
        self.assertEqual(response.status_code,200)
        ids={x["id"] for x in response.data}
        self.assertTrue({"waste_kl_city","waste_kl_county","dwd","nina_city","weather","telegram"}.issubset(ids))

    @patch("family.views.sync_source", return_value=3)
    def test_owner_can_connect_and_test_integration(self, sync_mock):
        response=self.client.post("/api/integrations/connect/",{
            "family":str(self.family.id),"catalog_id":"dwd","values":{"region":"Kaiserslautern"}
        },format="json")
        self.assertEqual(response.status_code,201)
        self.assertEqual(response.data["synced"],3)
        source=IntegrationSource.objects.get(family=self.family)
        self.assertEqual(source.config["adapter"],"dwd")
        sync_mock.assert_called_once()

    @patch("family.views.sync_source", return_value=0)
    def test_teen_cannot_manage_integrations(self, sync_mock):
        self.client.force_authenticate(self.teen)
        response=self.client.post("/api/integrations/connect/",{
            "family":str(self.family.id),"catalog_id":"nina_city","values":{}
        },format="json")
        self.assertEqual(response.status_code,403)
        self.assertFalse(IntegrationSource.objects.filter(family=self.family).exists())
        sync_mock.assert_not_called()

    def test_integration_secrets_are_redacted(self):
        source=IntegrationSource.objects.create(family=self.family,name="Telegram",kind="messenger",config={"adapter":"telegram","bot_token":"very-secret-token","chat_id":"123"})
        response=self.client.get(f"/api/integrations/{source.id}/")
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.data["config"]["bot_token"],"••••••••")
        self.assertEqual(response.data["config"]["chat_id"],"123")
