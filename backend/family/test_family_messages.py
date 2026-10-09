from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from .models import Family, InboxItem, InboxReceipt, Membership


class FamilyMessageTests(TestCase):
    def setUp(self):
        User=get_user_model()
        self.owner=User.objects.create_user("owner",password="pw")
        self.adult=User.objects.create_user("adult",password="pw")
        self.teen=User.objects.create_user("teen",password="pw")
        self.child=User.objects.create_user("child",password="pw")
        self.outsider=User.objects.create_user("outsider",password="pw")
        self.family=Family.objects.create(name="Familie",slug="familie")
        self.owner_m=Membership.objects.create(family=self.family,user=self.owner,role=Membership.Role.OWNER,display_name="Owner")
        self.adult_m=Membership.objects.create(family=self.family,user=self.adult,role=Membership.Role.ADULT,display_name="Adult")
        self.teen_m=Membership.objects.create(family=self.family,user=self.teen,role=Membership.Role.TEEN,display_name="Teen")
        self.child_m=Membership.objects.create(family=self.family,user=self.child,role=Membership.Role.CHILD,display_name="Child")
        self.other_family=Family.objects.create(name="Andere",slug="andere")
        Membership.objects.create(family=self.other_family,user=self.outsider,role=Membership.Role.OWNER)
        self.client=APIClient()

    @patch("family.message_views.notify_domain_event")
    def test_selected_message_is_only_visible_to_sender_and_recipient(self,notify):
        self.client.force_authenticate(self.adult)
        response=self.client.post("/api/inbox/",{"family":str(self.family.id),"body":"Nur für Teen","audience":"selected","recipient_ids":[str(self.teen_m.id)]},format="json")
        self.assertEqual(response.status_code,201)
        item=InboxItem.objects.get(source="manual_message")
        self.assertEqual(item.created_by,self.adult)
        self.assertEqual(InboxReceipt.objects.filter(item=item).count(),1)
        notify.assert_called_once()

        self.client.force_authenticate(self.teen)
        rows=self.client.get("/api/inbox/").data["results"]
        self.assertEqual(len(rows),1);self.assertTrue(rows[0]["unread"]);self.assertEqual(rows[0]["status"],"new")
        self.client.force_authenticate(self.child)
        self.assertEqual(self.client.get("/api/inbox/").data["results"],[])
        self.client.force_authenticate(self.adult)
        sent=self.client.get("/api/inbox/").data["results"][0]
        self.assertFalse(sent["unread"]);self.assertEqual(sent["status"],"sent")

    @patch("family.message_views.notify_domain_event")
    def test_read_state_is_per_recipient_and_sender_is_excluded(self,notify):
        self.client.force_authenticate(self.owner)
        response=self.client.post("/api/inbox/",{"family":str(self.family.id),"body":"An alle","audience":"family"},format="json")
        self.assertEqual(response.status_code,201);item_id=response.data["id"]
        self.assertFalse(InboxReceipt.objects.filter(item_id=item_id,membership=self.owner_m).exists())
        self.client.force_authenticate(self.adult)
        self.assertTrue(self.client.get("/api/inbox/").data["results"][0]["unread"])
        read=self.client.post(f"/api/inbox/{item_id}/read/",{},format="json")
        self.assertEqual(read.status_code,200);self.assertFalse(read.data["unread"]);self.assertEqual(read.data["status"],"read")
        self.client.force_authenticate(self.teen)
        self.assertTrue(self.client.get("/api/inbox/").data["results"][0]["unread"])

    @patch("family.message_views.notify_domain_event")
    def test_child_cannot_send_and_cross_tenant_recipient_is_rejected(self,notify):
        self.client.force_authenticate(self.child)
        denied=self.client.post("/api/inbox/",{"family":str(self.family.id),"body":"Nein"},format="json")
        self.assertEqual(denied.status_code,403)
        outsider_membership=Membership.objects.get(family=self.other_family,user=self.outsider)
        self.client.force_authenticate(self.adult)
        invalid=self.client.post("/api/inbox/",{"family":str(self.family.id),"body":"Leak","audience":"selected","recipient_ids":[str(outsider_membership.id)]},format="json")
        self.assertEqual(invalid.status_code,400)

    @patch("family.message_views.notify_domain_event")
    def test_sender_can_withdraw_and_owner_can_moderate(self,notify):
        self.client.force_authenticate(self.teen)
        created=self.client.post("/api/inbox/",{"family":str(self.family.id),"body":"Kurz"},format="json")
        item_id=created.data["id"]
        withdrawn=self.client.post(f"/api/inbox/{item_id}/withdraw/",{},format="json")
        self.assertEqual(withdrawn.status_code,200);self.assertEqual(withdrawn.data["status"],"withdrawn")
        self.client.force_authenticate(self.adult)
        self.assertEqual(self.client.get("/api/inbox/").data["results"],[])
        self.client.force_authenticate(self.owner)
        owner_rows=self.client.get("/api/inbox/").data["results"]
        self.assertEqual(len(owner_rows),1);self.assertTrue(owner_rows[0]["can_withdraw"])
