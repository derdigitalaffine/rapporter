from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from expenses.models import Expense
from .context_links import default_context_registry
from .models import Family, Membership, ShoppingItem
from .shopping_models import ShoppingSession, ShoppingSessionActivity


class ShoppingSessionTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user(username="session-owner", password="x")
        self.partner = User.objects.create_user(username="session-partner", password="x")
        self.hidden = User.objects.create_user(username="session-hidden", password="x")
        self.outsider = User.objects.create_user(username="session-outsider", password="x")
        self.family = Family.objects.create(name="Session Family", slug="session-family")
        self.other_family = Family.objects.create(name="Other Session Family", slug="other-session-family")
        self.owner_member = Membership.objects.create(family=self.family, user=self.owner, role=Membership.Role.OWNER, display_name="Owner")
        self.partner_member = Membership.objects.create(family=self.family, user=self.partner, role=Membership.Role.ADULT, display_name="Partner", avatar="🛒")
        self.hidden_member = Membership.objects.create(family=self.family, user=self.hidden, role=Membership.Role.TEEN, display_name="Hidden")
        Membership.objects.create(family=self.other_family, user=self.outsider, role=Membership.Role.OWNER, display_name="Outsider")
        self.owner_client = APIClient(); self.owner_client.force_authenticate(self.owner)
        self.partner_client = APIClient(); self.partner_client.force_authenticate(self.partner)
        self.hidden_client = APIClient(); self.hidden_client.force_authenticate(self.hidden)
        self.outsider_client = APIClient(); self.outsider_client.force_authenticate(self.outsider)
        created = self.owner_client.post("/api/shopping-lists/", {
            "family": str(self.family.id),
            "name": "Together",
            "visibility": "selected",
            "visible_members": [str(self.partner_member.id)],
        }, format="json")
        self.assertEqual(created.status_code, 201)
        self.list_id = created.data["id"]

    def start(self, client=None):
        return (client or self.owner_client).post(
            "/api/shopping-sessions/start/",
            {"shopping_list": self.list_id},
            format="json",
        )

    def add_item(self, name, *, checked=False, client=None):
        client = client or self.owner_client
        created = client.post(
            "/api/shopping-items/",
            {"shopping_list": self.list_id, "name": name},
            format="json",
        )
        self.assertEqual(created.status_code, 201)
        if checked:
            updated = client.patch(f"/api/shopping-items/{created.data['id']}/", {"checked": True}, format="json")
            self.assertEqual(updated.status_code, 200)
        return created.data["id"]

    def test_authorized_users_join_same_active_session(self):
        first = self.start()
        second = self.start(self.partner_client)
        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(first.data["session"]["id"], second.data["session"]["id"])
        self.assertEqual(ShoppingSession.objects.filter(shopping_list_id=self.list_id, status="active").count(), 1)
        names = {row["name"] for row in second.data["session"]["participants"]}
        self.assertEqual(names, {"Owner", "Partner"})

    def test_hidden_and_cross_family_users_cannot_probe_session(self):
        self.start()
        for client in (self.hidden_client, self.outsider_client):
            started = client.post("/api/shopping-sessions/start/", {"shopping_list": self.list_id}, format="json")
            current = client.get(f"/api/shopping-sessions/current/?shopping_list={self.list_id}&after=0")
            self.assertEqual(started.status_code, 404)
            self.assertEqual(current.status_code, 404)

    def test_check_activity_is_incremental_and_retry_idempotent(self):
        self.start()
        item_response = self.owner_client.post(
            "/api/shopping-items/",
            {"shopping_list": self.list_id, "name": "Milk"},
            format="json",
        )
        self.assertEqual(item_response.status_code, 201)
        item_id = item_response.data["id"]
        initial = self.partner_client.get(f"/api/shopping-sessions/current/?shopping_list={self.list_id}&after=0")
        self.assertEqual(initial.status_code, 200)
        self.assertEqual([row["kind"] for row in initial.data["activities"]], ["item_added"])
        cursor = initial.data["cursor"]

        checked = self.owner_client.patch(f"/api/shopping-items/{item_id}/", {"checked": True}, format="json")
        retried = self.owner_client.patch(f"/api/shopping-items/{item_id}/", {"checked": True}, format="json")
        self.assertEqual(checked.status_code, 200)
        self.assertEqual(retried.status_code, 200)

        delta = self.partner_client.get(f"/api/shopping-sessions/current/?shopping_list={self.list_id}&after={cursor}")
        self.assertEqual(delta.status_code, 200)
        self.assertEqual(len(delta.data["activities"]), 1)
        self.assertEqual(delta.data["activities"][0]["kind"], "item_checked")
        self.assertEqual(delta.data["activities"][0]["actor"]["name"], "Owner")
        self.assertTrue(delta.data["activities"][0]["item"]["checked"])
        self.assertEqual(ShoppingSessionActivity.objects.filter(session_id=first_session_id(self.list_id), kind="item_checked").count(), 1)

    def test_quick_add_retry_records_one_add_activity(self):
        self.start()
        payload = {"family": str(self.family.id), "shopping_list": self.list_id, "name": "Bread"}
        first = self.owner_client.post("/api/smart/shopping/quick-add/", payload, format="json")
        second = self.owner_client.post("/api/smart/shopping/quick-add/", payload, format="json")
        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 200)
        session = ShoppingSession.objects.get(shopping_list_id=self.list_id, status="active")
        self.assertEqual(session.activities.filter(kind="item_added", item_name="Bread").count(), 1)

    def test_hidden_gift_item_never_enters_activity_stream(self):
        self.start()
        shopping_list = ShoppingSession.objects.get(shopping_list_id=self.list_id).shopping_list
        ShoppingItem.objects.create(
            shopping_list=shopping_list,
            name="Surprise",
            added_by=self.owner,
            hidden_from_user=self.partner,
        )
        session = ShoppingSession.objects.get(shopping_list_id=self.list_id, status="active")
        self.assertFalse(session.activities.filter(item_name="Surprise").exists())

    def test_item_hidden_after_activity_does_not_leak_snapshot_name(self):
        self.start()
        created = self.owner_client.post(
            "/api/shopping-items/",
            {"shopping_list": self.list_id, "name": "Later secret"},
            format="json",
        )
        self.assertEqual(created.status_code, 201)
        item = ShoppingItem.objects.get(id=created.data["id"])
        item.hidden_from_user = self.partner
        item.save(update_fields=["hidden_from_user"])

        delta = self.partner_client.get(f"/api/shopping-sessions/current/?shopping_list={self.list_id}&after=0")
        self.assertEqual(delta.status_code, 200)
        self.assertEqual(delta.data["activities"], [])
        self.assertGreaterEqual(delta.data["cursor"], 1)
        self.assertNotIn("Later secret", str(delta.data))

    def test_completion_requires_explicit_open_item_choice_and_is_idempotent(self):
        started = self.start()
        purchased_id = self.add_item("Milk", checked=True)
        open_id = self.add_item("Bread")
        session_id = started.data["session"]["id"]

        missing_choice = self.owner_client.post(
            "/api/shopping-sessions/complete/",
            {"shopping_list": self.list_id, "session": session_id},
            format="json",
        )
        self.assertEqual(missing_choice.status_code, 409)
        self.assertEqual(missing_choice.data["code"], "open_items_choice_required")

        completed = self.owner_client.post(
            "/api/shopping-sessions/complete/",
            {"shopping_list": self.list_id, "session": session_id, "open_items": "keep"},
            format="json",
        )
        self.assertEqual(completed.status_code, 200)
        self.assertEqual(completed.data["completion"]["purchased_count"], 1)
        self.assertEqual(completed.data["completion"]["open_count"], 1)
        self.assertEqual(completed.data["completion"]["open_items_policy"], "keep")
        self.assertEqual(completed.data["context_ref"], {"type": "shopping_session", "id": session_id})
        self.assertFalse(ShoppingItem.objects.filter(id=purchased_id).exists())
        self.assertTrue(ShoppingItem.objects.filter(id=open_id).exists())
        self.assertEqual(Expense.objects.filter(family=self.family).count(), 0)

        session = ShoppingSession.objects.get(id=session_id)
        original_snapshot = session.snapshot
        self.assertEqual(session.status, ShoppingSession.Status.COMPLETED)
        self.assertEqual(session.completed_by, self.owner)
        self.assertEqual(original_snapshot["purchased_items"][0]["name"], "Milk")

        retried = self.owner_client.post(
            "/api/shopping-sessions/complete/",
            {"shopping_list": self.list_id, "session": session_id, "open_items": "remove"},
            format="json",
        )
        self.assertEqual(retried.status_code, 200)
        session.refresh_from_db()
        self.assertEqual(session.snapshot, original_snapshot)
        self.assertTrue(ShoppingItem.objects.filter(id=open_id).exists())

        next_session = self.start()
        self.assertEqual(next_session.status_code, 201)
        self.assertNotEqual(next_session.data["session"]["id"], session_id)

    def test_completion_can_remove_visible_open_items(self):
        started = self.start()
        self.add_item("Milk", checked=True)
        open_id = self.add_item("Bread")
        response = self.owner_client.post(
            "/api/shopping-sessions/complete/",
            {"shopping_list": self.list_id, "session": started.data["session"]["id"], "open_items": "remove"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(ShoppingItem.objects.filter(id=open_id).exists())
        self.assertEqual(response.data["completion"]["open_items"][0]["name"], "Bread")

    def test_completion_does_not_snapshot_or_delete_item_hidden_from_actor(self):
        started = self.start(self.partner_client)
        self.add_item("Visible milk", checked=True, client=self.partner_client)
        shopping_list = ShoppingSession.objects.get(id=started.data["session"]["id"]).shopping_list
        secret = ShoppingItem.objects.create(
            shopping_list=shopping_list,
            name="Gift",
            checked=True,
            added_by=self.owner,
            hidden_from_user=self.partner,
        )
        response = self.partner_client.post(
            "/api/shopping-sessions/complete/",
            {"shopping_list": self.list_id, "session": started.data["session"]["id"], "open_items": "keep"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("Gift", str(response.data["completion"]))
        self.assertTrue(ShoppingItem.objects.filter(id=secret.id).exists())

    def test_checkout_context_registry_links_expense_to_session(self):
        registry = default_context_registry()
        self.assertIn("shopping_session", registry._types)
        self.assertIn("expense", registry._types)
        self.assertTrue(registry._relations["context"].allows("expense", "shopping_session"))


def first_session_id(list_id):
    return ShoppingSession.objects.get(shopping_list_id=list_id, status="active").id
