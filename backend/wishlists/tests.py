from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from expenses.models import Expense
from family.birthday_context_models import BirthdayOccasion
from family.context_models import ContextLink
from family.models import Family, Membership, ShoppingList, Task

from .models import WishlistReservation


class WishlistApiTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user(username="owner", password="pw")
        self.giver = User.objects.create_user(username="giver", password="pw")
        self.second_giver = User.objects.create_user(username="giver2", password="pw")
        self.teen = User.objects.create_user(username="teen", password="pw")
        self.outsider = User.objects.create_user(username="outsider", password="pw")
        self.family = Family.objects.create(name="Alpha", slug="wishlist-alpha")
        self.other_family = Family.objects.create(name="Beta", slug="wishlist-beta")
        self.owner_membership = Membership.objects.create(family=self.family, user=self.owner, role=Membership.Role.OWNER, display_name="Owner")
        self.giver_membership = Membership.objects.create(family=self.family, user=self.giver, role=Membership.Role.ADULT, display_name="Giver")
        self.second_giver_membership = Membership.objects.create(family=self.family, user=self.second_giver, role=Membership.Role.ADULT, display_name="Giver 2")
        self.teen_membership = Membership.objects.create(family=self.family, user=self.teen, role=Membership.Role.TEEN, display_name="Teen")
        Membership.objects.create(family=self.other_family, user=self.outsider, role=Membership.Role.OWNER)
        self.client = APIClient()
        self.client.force_authenticate(self.owner)

    def client_for(self, user):
        client = APIClient()
        client.force_authenticate(user)
        return client

    def create_wishlist(self, *, visibility="family", access=None):
        payload = {"family": str(self.family.id), "title": "Meine Wünsche", "visibility": visibility}
        if access is not None:
            payload["access"] = [{"membership": str(membership.id)} for membership in access]
        response = self.client.post("/api/wishlists/", payload, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        return response.data

    def add_item(self, wishlist_id, **overrides):
        payload = {"title": "Kopfhörer", "url": "https://Example.COM/products/1#details", "note": "Over-ear", "priority": "high"}
        payload.update(overrides)
        response = self.client.post(f"/api/wishlists/{wishlist_id}/items/", payload, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        return response.data

    def test_family_wishlist_item_accepts_https_and_normalizes_without_fetching(self):
        wishlist = self.create_wishlist()
        item = self.add_item(wishlist["id"])
        self.assertEqual(item["url"], "https://example.com/products/1")
        self.assertEqual(item["title"], "Kopfhörer")
        invalid = self.client.post(f"/api/wishlists/{wishlist['id']}/items/", {"title": "Unsicher", "url": "http://example.com/x"}, format="json")
        self.assertEqual(invalid.status_code, 400)
        credentials = self.client.post(f"/api/wishlists/{wishlist['id']}/items/", {"title": "Secret", "url": "https://user:pass@example.com/x"}, format="json")
        self.assertEqual(credentials.status_code, 400)

    def test_selected_visibility_is_server_side_and_projection_does_not_expand_it(self):
        wishlist = self.create_wishlist(visibility="selected", access=[self.giver_membership])
        item = self.add_item(wishlist["id"])
        giver_client = self.client_for(self.giver)
        visible = giver_client.get(f"/api/wishlists/?family={self.family.id}")
        self.assertEqual(visible.status_code, 200)
        self.assertEqual(len(visible.data), 1)
        second_client = self.client_for(self.second_giver)
        hidden = second_client.get(f"/api/wishlists/?family={self.family.id}")
        self.assertEqual(hidden.status_code, 200)
        self.assertEqual(hidden.data, [])
        self.assertEqual(second_client.get(f"/api/wishlists/{wishlist['id']}/").status_code, 404)
        blocked = giver_client.post(f"/api/wishlist-items/{item['id']}/actions/", {"confirmed": True, "action": "task"}, format="json")
        self.assertEqual(blocked.status_code, 409)
        self.assertEqual(blocked.data["code"], "selected_wishlist_action")
        self.assertFalse(Task.objects.exists())

    def test_owner_never_receives_reservation_metadata_but_gifters_do(self):
        wishlist = self.create_wishlist()
        item = self.add_item(wishlist["id"])
        giver_client = self.client_for(self.giver)
        reserved = giver_client.post(f"/api/wishlist-items/{item['id']}/reservation/", {"status": "reserved", "note": "Schon bestellt"}, format="json")
        self.assertEqual(reserved.status_code, 200, reserved.data)
        self.assertEqual(reserved.data["reservation"]["reserved_by"]["id"], str(self.giver_membership.id))
        self.assertTrue(reserved.data["reservation"]["mine"])
        owner_view = self.client.get(f"/api/wishlists/{wishlist['id']}/")
        self.assertEqual(owner_view.status_code, 200)
        self.assertNotIn("reservation", owner_view.data["items"][0])
        self.assertEqual(self.client.post(f"/api/wishlist-items/{item['id']}/reservation/", {"status": "reserved"}, format="json").status_code, 404)
        other_view = self.client_for(self.second_giver).get(f"/api/wishlists/{wishlist['id']}/")
        self.assertEqual(other_view.data["items"][0]["reservation"]["note"], "Schon bestellt")
        self.assertFalse(other_view.data["items"][0]["reservation"]["mine"])

    def test_reservation_has_single_holder_and_release_is_owner_specific(self):
        wishlist = self.create_wishlist()
        item = self.add_item(wishlist["id"])
        giver_client = self.client_for(self.giver)
        second_client = self.client_for(self.second_giver)
        self.assertEqual(giver_client.post(f"/api/wishlist-items/{item['id']}/reservation/", {"status": "reserved"}, format="json").status_code, 200)
        conflict = second_client.post(f"/api/wishlist-items/{item['id']}/reservation/", {"status": "purchased"}, format="json")
        self.assertEqual(conflict.status_code, 409)
        self.assertEqual(conflict.data["code"], "already_reserved")
        self.assertEqual(WishlistReservation.objects.count(), 1)
        self.assertEqual(second_client.delete(f"/api/wishlist-items/{item['id']}/reservation/").status_code, 404)
        self.assertEqual(giver_client.delete(f"/api/wishlist-items/{item['id']}/reservation/").status_code, 200)
        self.assertFalse(WishlistReservation.objects.exists())

    def test_teen_can_coordinate_visible_wishes_but_cannot_create_core_list(self):
        create = self.client_for(self.teen).post("/api/wishlists/", {"family": str(self.family.id), "title": "Teen list", "visibility": "family"}, format="json")
        self.assertEqual(create.status_code, 404)
        wishlist = self.create_wishlist()
        item = self.add_item(wishlist["id"])
        reserve = self.client_for(self.teen).post(f"/api/wishlist-items/{item['id']}/reservation/", {"status": "reserved"}, format="json")
        self.assertEqual(reserve.status_code, 200)

    def test_task_and_shopping_projection_are_canonical_and_hidden_from_owner(self):
        wishlist = self.create_wishlist()
        item = self.add_item(wishlist["id"])
        shopping_list = ShoppingList.objects.create(family=self.family, name="Geschenke")
        giver_client = self.client_for(self.giver)
        task_response = giver_client.post(f"/api/wishlist-items/{item['id']}/actions/", {"confirmed": True, "action": "task", "title": "Kopfhörer organisieren"}, format="json")
        self.assertEqual(task_response.status_code, 201, task_response.data)
        task = Task.objects.get(id=task_response.data["id"])
        self.assertEqual(task.hidden_from_user, self.owner)
        self.assertEqual(task.source, f"wishlist:{item['id']}")
        self.assertTrue(ContextLink.objects.filter(source_type="wishlist_item", source_id=item["id"], context_type="task", context_id=task.id, relation_key="wishlist.action").exists())
        shopping_response = giver_client.post(f"/api/wishlist-items/{item['id']}/actions/", {"confirmed": True, "action": "shopping", "shopping_list": str(shopping_list.id)}, format="json")
        self.assertEqual(shopping_response.status_code, 201, shopping_response.data)
        shopping_item = shopping_list.items.get(id=shopping_response.data["id"])
        self.assertEqual(shopping_item.hidden_from_user, self.owner)

    def test_expense_requires_second_explicit_family_visibility_acknowledgement(self):
        wishlist = self.create_wishlist()
        item = self.add_item(wishlist["id"])
        giver_client = self.client_for(self.giver)
        blocked = giver_client.post(f"/api/wishlist-items/{item['id']}/actions/", {"confirmed": True, "action": "expense", "amount": "49.90"}, format="json")
        self.assertEqual(blocked.status_code, 409)
        self.assertEqual(blocked.data["code"], "expense_family_visibility")
        self.assertFalse(Expense.objects.exists())
        accepted = giver_client.post(f"/api/wishlist-items/{item['id']}/actions/", {"confirmed": True, "action": "expense", "amount": "49.90", "currency": "eur", "acknowledge_family_visibility": True}, format="json")
        self.assertEqual(accepted.status_code, 201, accepted.data)
        expense = Expense.objects.get(id=accepted.data["id"])
        self.assertEqual(str(expense.total_amount), "49.90")
        self.assertEqual(expense.currency, "EUR")

    def test_follow_up_never_happens_without_confirmation(self):
        wishlist = self.create_wishlist()
        item = self.add_item(wishlist["id"])
        response = self.client_for(self.giver).post(f"/api/wishlist-items/{item['id']}/actions/", {"action": "task"}, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertFalse(Task.objects.exists())

    def test_birthday_context_uses_canonical_context_link_and_does_not_change_acl(self):
        wishlist = self.create_wishlist(visibility="selected")
        occasion = BirthdayOccasion.objects.create(family=self.family, membership=self.giver_membership, occurrence_year=2027, created_by=self.owner)
        response = self.client.post(f"/api/wishlists/{wishlist['id']}/context/", {"confirmed": True, "context_type": "birthday_occasion", "context_id": str(occasion.id), "relation_key": "birthday.wishlist"}, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertTrue(ContextLink.objects.filter(family=self.family, source_type="wishlist", source_id=wishlist["id"], context_type="birthday_occasion", context_id=occasion.id, relation_key="birthday.wishlist").exists())
        self.assertEqual(self.client_for(self.giver).get(f"/api/wishlists/{wishlist['id']}/").status_code, 404)

    def test_cross_family_ids_fail_closed(self):
        wishlist = self.create_wishlist()
        outsider = self.client_for(self.outsider)
        self.assertEqual(outsider.get(f"/api/wishlists/{wishlist['id']}/").status_code, 404)
        self.assertEqual(outsider.get(f"/api/wishlists/?family={self.family.id}").status_code, 404)
