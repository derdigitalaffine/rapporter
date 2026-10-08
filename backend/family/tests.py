from datetime import timedelta
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from .integrations import sync_ics
from .models import Family, Membership, FamilyInvitation, Task, InboxItem, ShoppingItem, IntegrationSource, FamilyEvent


class FamilyApiTests(TestCase):
    def setUp(self):
        User=get_user_model()
        self.alice=User.objects.create_user(username="alice",password="test-pass-123",email="alice@example.com")
        self.bob=User.objects.create_user(username="bob",password="test-pass-123",email="bob@example.com")
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

    def test_inbox_item_can_be_converted_to_task(self):
        item=InboxItem.objects.create(family=self.family,title="Milch holen",body="Bitte heute",source="share")
        response=self.client.post(f"/api/inbox/{item.id}/to_task/",{},format="json")
        self.assertEqual(response.status_code,201)

    def test_inbox_item_can_be_converted_to_shopping(self):
        item=InboxItem.objects.create(family=self.family,title="Äpfel",source="share")
        response=self.client.post(f"/api/inbox/{item.id}/to_shopping/",{},format="json")
        self.assertEqual(response.status_code,201)

    def test_integration_catalog_is_available_in_app_api(self):
        response=self.client.get("/api/integrations/catalog/")
        self.assertEqual(response.status_code,200)
        ids={x["id"] for x in response.data}
        self.assertTrue({"waste_kl_city","waste_kl_county","dwd","nina_city","weather","telegram"}.issubset(ids))

    @patch("family.views.sync_source", return_value=3)
    def test_owner_can_connect_and_test_integration(self, sync_mock):
        response=self.client.post("/api/integrations/connect/",{"family":str(self.family.id),"catalog_id":"dwd","values":{"region":"Kaiserslautern"}},format="json")
        self.assertEqual(response.status_code,201)

    @patch("family.views.sync_source", return_value=0)
    def test_teen_cannot_manage_integrations(self, sync_mock):
        self.client.force_authenticate(self.teen)
        response=self.client.post("/api/integrations/connect/",{"family":str(self.family.id),"catalog_id":"nina_city","values":{}},format="json")
        self.assertEqual(response.status_code,403)

    def test_integration_secrets_are_redacted(self):
        source=IntegrationSource.objects.create(family=self.family,name="Telegram",kind="messenger",config={"adapter":"telegram","bot_token":"very-secret-token","chat_id":"123"})
        response=self.client.get(f"/api/integrations/{source.id}/")
        self.assertEqual(response.data["config"]["bot_token"],"••••••••")

    @patch("family.integrations._get")
    def test_waste_ics_creates_event_and_reminder(self, mocked_get):
        tomorrow=timezone.localdate()+timedelta(days=1)
        ics=f"""BEGIN:VCALENDAR\nVERSION:2.0\nBEGIN:VEVENT\nUID:waste-1\nDTSTART;VALUE=DATE:{tomorrow:%Y%m%d}\nSUMMARY:Restmüll\nEND:VEVENT\nEND:VCALENDAR\n""".encode()
        response=Mock();response.content=ics;mocked_get.return_value=response
        source=IntegrationSource.objects.create(family=self.family,name="Müll",kind="waste",endpoint="https://example.org/waste.ics",config={"adapter":"waste_kl_city"})
        self.assertEqual(sync_ics(source),1)
        self.assertTrue(Task.objects.filter(family=self.family,title="Restmüll rausstellen",source__startswith="waste:").exists())

    def test_owner_creates_invitation_and_public_info_is_readable(self):
        expires=(timezone.now()+timedelta(days=7)).isoformat()
        response=self.client.post("/api/invitations/",{"family":str(self.family.id),"role":"adult","email":"new@example.com","expires_at":expires},format="json")
        self.assertEqual(response.status_code,201)
        token=response.data["token"]
        public=APIClient().get(f"/api/invite/{token}/")
        self.assertEqual(public.status_code,200)
        self.assertEqual(public.data["family_name"],"Alice Family")

    def test_invite_registers_user_and_is_single_use(self):
        invite=FamilyInvitation.objects.create(family=self.family,role="adult",email="new@example.com",invited_by=self.alice,expires_at=timezone.now()+timedelta(days=7))
        anon=APIClient()
        response=anon.post(f"/api/invite/{invite.token}/register/",{"username":"newperson","email":"new@example.com","password":"very-secure-123","display_name":"New Person"},format="json")
        self.assertEqual(response.status_code,201)
        user=get_user_model().objects.get(username="newperson")
        self.assertTrue(Membership.objects.filter(family=self.family,user=user,role="adult").exists())
        second=anon.post(f"/api/invite/{invite.token}/register/",{"username":"another","email":"new@example.com","password":"very-secure-123"},format="json")
        self.assertEqual(second.status_code,400)

    def test_email_bound_invite_rejects_wrong_email(self):
        invite=FamilyInvitation.objects.create(family=self.family,role="adult",email="target@example.com",invited_by=self.alice,expires_at=timezone.now()+timedelta(days=7))
        anon=APIClient()
        response=anon.post(f"/api/invite/{invite.token}/register/",{"username":"wronguser","email":"wrong@example.com","password":"very-secure-123"},format="json")
        self.assertEqual(response.status_code,403)

    def test_existing_user_accepts_invitation(self):
        invite=FamilyInvitation.objects.create(family=self.family,role="guest",email="bob@example.com",invited_by=self.alice,expires_at=timezone.now()+timedelta(days=7))
        client=APIClient();client.force_authenticate(self.bob)
        response=client.post(f"/api/invite/{invite.token}/accept/",{},format="json")
        self.assertEqual(response.status_code,200)
        self.assertTrue(Membership.objects.filter(family=self.family,user=self.bob,role="guest").exists())
