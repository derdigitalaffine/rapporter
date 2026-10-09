import os
from datetime import timedelta
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from .automation import run_rule
from .integration_health import sync_with_health
from .integrations import sync_ics
from .models import (
    AutomationRule,
    EntryMemory,
    Family,
    FamilyEvent,
    FamilyInvitation,
    InboxItem,
    IntegrationSource,
    Membership,
    PushSubscription,
    ShoppingItem,
    ShoppingList,
    Task,
    TaskList,
)


class FamilyApiTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.alice = User.objects.create_user(username="alice", password="test-pass-123", email="alice@example.com")
        self.bob = User.objects.create_user(username="bob", password="test-pass-123", email="bob@example.com")
        self.teen = User.objects.create_user(username="teen", password="test-pass-123", email="teen@example.com")
        self.family = Family.objects.create(name="Alice Family", slug="alice-family")
        self.other = Family.objects.create(name="Bob Family", slug="bob-family")
        self.alice_membership = Membership.objects.create(family=self.family, user=self.alice, role=Membership.Role.OWNER, display_name="Alice")
        Membership.objects.create(family=self.family, user=self.teen, role=Membership.Role.TEEN, display_name="Teen")
        Membership.objects.create(family=self.other, user=self.bob, role=Membership.Role.OWNER, display_name="Bob")
        self.task_list = TaskList.objects.create(family=self.family, name="Allgemein")
        self.other_task_list = TaskList.objects.create(family=self.other, name="Privat")
        self.shopping = ShoppingList.objects.create(family=self.family, name="Einkauf")
        self.client = APIClient()
        self.client.force_authenticate(self.alice)

    def rows(self, response):
        return response.data.get("results", response.data)

    def test_tasks_are_isolated_by_family(self):
        own = Task.objects.create(family=self.family, task_list=self.task_list, title="Own", created_by=self.alice)
        Task.objects.create(family=self.other, task_list=self.other_task_list, title="Secret", created_by=self.bob)
        response = self.client.get("/api/tasks/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual({str(item["id"]) for item in self.rows(response)}, {str(own.id)})

    def test_cannot_create_or_move_task_to_other_family(self):
        response = self.client.post("/api/tasks/", {"family": str(self.other.id), "title": "Nope"}, format="json")
        self.assertEqual(response.status_code, 403)
        own = Task.objects.create(family=self.family, task_list=self.task_list, title="Own", created_by=self.alice)
        response = self.client.patch(f"/api/tasks/{own.id}/", {"family": str(self.other.id), "task_list": str(self.other_task_list.id)}, format="json")
        self.assertIn(response.status_code, {400, 403})
        own.refresh_from_db()
        self.assertEqual(own.family_id, self.family.id)

    def test_task_assignee_must_belong_to_family(self):
        task = Task.objects.create(family=self.family, task_list=self.task_list, title="Own", created_by=self.alice)
        response = self.client.patch(f"/api/tasks/{task.id}/", {"assignee": self.bob.id}, format="json")
        self.assertEqual(response.status_code, 400)

    def test_inbox_item_can_be_converted_to_task_and_shopping(self):
        task_item = InboxItem.objects.create(family=self.family, title="Milch holen", body="Bitte heute", source="share")
        response = self.client.post(f"/api/inbox/{task_item.id}/to_task/", {}, format="json")
        self.assertEqual(response.status_code, 201)
        shop_item = InboxItem.objects.create(family=self.family, title="Äpfel", source="share")
        response = self.client.post(f"/api/inbox/{shop_item.id}/to_shopping/", {}, format="json")
        self.assertEqual(response.status_code, 201)

    def test_smart_catalog_contains_extended_integrations(self):
        response = self.client.get("/api/integration-hub/catalog/")
        self.assertEqual(response.status_code, 200)
        ids = {item["id"] for item in response.data}
        expected = {
            "waste_kl_city", "waste_kl_county", "dwd", "nina_city", "weather", "telegram",
            "google_oauth", "microsoft_oauth", "google_ics", "microsoft_ics", "webuntis", "moodle",
            "home_assistant", "vrn",
        }
        self.assertTrue(expected.issubset(ids))

    @patch("family.smart_views.sync_with_health", return_value=3)
    def test_owner_can_connect_extended_integration(self, sync_mock):
        response = self.client.post(
            "/api/integration-hub/connect/",
            {"family": str(self.family.id), "catalog_id": "vrn", "values": {"stop_id": "de:07312:123"}},
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["synced"], 3)

    @patch("family.smart_views.sync_with_health", return_value=0)
    def test_teen_cannot_manage_integrations(self, sync_mock):
        self.client.force_authenticate(self.teen)
        response = self.client.post(
            "/api/integration-hub/connect/",
            {"family": str(self.family.id), "catalog_id": "nina_city", "values": {}},
            format="json",
        )
        self.assertEqual(response.status_code, 403)

    def test_integration_secrets_and_private_calendar_endpoint_are_redacted(self):
        source = IntegrationSource.objects.create(
            family=self.family,
            name="Private calendar",
            kind=IntegrationSource.Kind.ICS,
            endpoint="https://calendar.example/very-secret-token.ics",
            config={"adapter": "google_ics", "access_token": "access", "refresh_token": "refresh", "secret_endpoint": True},
        )
        response = self.client.get(f"/api/integrations/{source.id}/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["endpoint"], "••••••••")
        self.assertEqual(response.data["config"]["access_token"], "••••••••")
        self.assertEqual(response.data["config"]["refresh_token"], "••••••••")

    @patch("family.integrations._get")
    def test_waste_ics_creates_event_then_rule_creates_single_task(self, mocked_get):
        tomorrow = timezone.localdate() + timedelta(days=1)
        ics = f"""BEGIN:VCALENDAR\nVERSION:2.0\nBEGIN:VEVENT\nUID:waste-1\nDTSTART;VALUE=DATE:{tomorrow:%Y%m%d}\nSUMMARY:Restmüll\nEND:VEVENT\nEND:VCALENDAR\n""".encode()
        http = Mock(); http.content = ics; mocked_get.return_value = http
        source = IntegrationSource.objects.create(
            family=self.family,
            name="Müll",
            kind=IntegrationSource.Kind.WASTE,
            endpoint="https://example.org/waste.ics",
            config={"adapter": "waste_kl_city"},
        )
        self.assertEqual(sync_ics(source), 1)
        self.assertTrue(FamilyEvent.objects.filter(family=self.family, type="waste.collection", title="Restmüll").exists())
        rule = AutomationRule.objects.create(
            family=self.family,
            name="Müll rausstellen",
            trigger_type=AutomationRule.Trigger.WASTE_TOMORROW,
            action_type=AutomationRule.Action.TASK_CREATE,
            action_config={"title": "{event_title} rausstellen"},
        )
        self.assertEqual(run_rule(rule), 1)
        self.assertTrue(Task.objects.filter(family=self.family, title="Restmüll rausstellen", source=f"rule:{rule.id}").exists())
        self.assertEqual(run_rule(rule), 0)
        self.assertEqual(Task.objects.filter(family=self.family, title="Restmüll rausstellen").count(), 1)

    def test_smart_task_quick_add_deduplicates_open_task(self):
        payload = {"family": str(self.family.id), "task_list": str(self.task_list.id), "title": "Sporttasche packen", "priority": "high", "estimate_minutes": 10}
        first = self.client.post("/api/smart/tasks/quick-add/", payload, format="json")
        second = self.client.post("/api/smart/tasks/quick-add/", payload, format="json")
        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 200)
        self.assertTrue(second.data["reused"])
        self.assertEqual(Task.objects.filter(family=self.family, title="Sporttasche packen", completed_at__isnull=True).count(), 1)

    def test_shopping_quick_add_reopens_checked_item(self):
        item = ShoppingItem.objects.create(shopping_list=self.shopping, name="Milch", quantity="2", category="Kühlung", checked=True, checked_at=timezone.now())
        response = self.client.post(
            "/api/smart/shopping/quick-add/",
            {"family": str(self.family.id), "shopping_list": str(self.shopping.id), "name": "Milch", "quantity": "3"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        item.refresh_from_db()
        self.assertFalse(item.checked)
        self.assertIsNone(item.checked_at)
        self.assertEqual(item.quantity, "3")

    def test_family_memory_survives_deleting_original_entries(self):
        task = Task.objects.create(family=self.family, task_list=self.task_list, title="Keller fegen", notes="Besen holen", created_by=self.alice)
        item = ShoppingItem.objects.create(shopping_list=self.shopping, name="Hafermilch", quantity="2", category="Getränke")
        self.assertTrue(EntryMemory.objects.filter(family=self.family, kind="task", normalized_name="keller fegen").exists())
        self.assertTrue(EntryMemory.objects.filter(family=self.family, kind="shopping", normalized_name="hafermilch").exists())
        task.delete(); item.delete()
        task_suggestions = self.client.get(f"/api/tasks/suggestions/?family={self.family.id}&q=Keller")
        shopping_suggestions = self.client.get(f"/api/shopping-items/suggestions/?family={self.family.id}&q=Hafer")
        self.assertEqual(task_suggestions.status_code, 200)
        self.assertEqual(shopping_suggestions.status_code, 200)
        self.assertEqual(task_suggestions.data[0]["name"], "Keller fegen")
        self.assertEqual(task_suggestions.data[0]["notes"], "Besen holen")
        self.assertEqual(shopping_suggestions.data[0]["quantity"], "2")
        self.assertEqual(shopping_suggestions.data[0]["category"], "Getränke")

    def test_transit_delay_rule_creates_inbox_once(self):
        event = FamilyEvent.objects.create(
            family=self.family,
            type="transit.departure",
            title="101 → Hauptbahnhof",
            starts_at=timezone.now() + timedelta(minutes=20),
            payload={"line": "101", "destination": "Hauptbahnhof", "stop": "Rathaus", "delay_minutes": 15},
        )
        rule = AutomationRule.objects.create(
            family=self.family,
            name="Verspätung",
            trigger_type=AutomationRule.Trigger.TRANSIT_DELAY,
            trigger_config={"minutes": 10, "within_hours": 2},
            action_type=AutomationRule.Action.INBOX_CREATE,
            action_config={"title": "{line} verspätet", "body": "{delay_minutes} Minuten"},
        )
        self.assertEqual(run_rule(rule), 1)
        self.assertEqual(run_rule(rule), 0)
        inbox = InboxItem.objects.get(family=self.family, source="automation")
        self.assertEqual(inbox.title, "101 verspätet")
        self.assertIn("15", inbox.body)

    def test_task_completed_rule_can_add_shopping_item(self):
        task = Task.objects.create(family=self.family, task_list=self.task_list, title="Waschmittel prüfen", completed_at=timezone.now(), created_by=self.alice)
        rule = AutomationRule.objects.create(
            family=self.family,
            name="Nachfüllen",
            trigger_type=AutomationRule.Trigger.TASK_COMPLETED,
            trigger_config={"title_contains": "Waschmittel"},
            action_type=AutomationRule.Action.SHOPPING_ADD,
            action_config={"name": "Waschmittel", "quantity": "1"},
        )
        self.assertEqual(run_rule(rule), 1)
        self.assertTrue(ShoppingItem.objects.filter(shopping_list=self.shopping, name="Waschmittel", checked=False).exists())

    @patch("family.integration_health.raw_sync_source", side_effect=ValueError("provider down"))
    def test_integration_failure_is_persisted_with_backoff(self, mocked_sync):
        source = IntegrationSource.objects.create(family=self.family, name="Provider", kind=IntegrationSource.Kind.GENERIC)
        with self.assertRaises(ValueError):
            sync_with_health(source)
        source.refresh_from_db()
        self.assertEqual(source.last_sync_status, "error")
        self.assertIn("provider down", source.last_sync_error)
        self.assertEqual(source.consecutive_failures, 1)
        self.assertGreater(source.next_sync_at, timezone.now())

    @patch("family.integration_health.raw_sync_source", return_value=2)
    def test_integration_success_clears_previous_error(self, mocked_sync):
        source = IntegrationSource.objects.create(
            family=self.family,
            name="Provider",
            kind=IntegrationSource.Kind.GENERIC,
            last_sync_status="error",
            last_sync_error="old",
            consecutive_failures=3,
            next_sync_at=timezone.now() + timedelta(hours=1),
        )
        self.assertEqual(sync_with_health(source, force=True), 2)
        source.refresh_from_db()
        self.assertEqual(source.last_sync_status, "success")
        self.assertEqual(source.last_sync_error, "")
        self.assertEqual(source.consecutive_failures, 0)
        self.assertIsNone(source.next_sync_at)
        self.assertIsNotNone(source.last_success_at)

    def test_last_owner_cannot_be_demoted_or_removed(self):
        response = self.client.patch(f"/api/memberships/{self.alice_membership.id}/", {"role": "adult"}, format="json")
        self.assertEqual(response.status_code, 400)
        response = self.client.delete(f"/api/memberships/{self.alice_membership.id}/")
        self.assertEqual(response.status_code, 400)

    def test_owner_can_change_teen_role(self):
        membership = Membership.objects.get(family=self.family, user=self.teen)
        response = self.client.patch(f"/api/memberships/{membership.id}/", {"role": "child", "display_name": "Kid"}, format="json")
        self.assertEqual(response.status_code, 200)
        membership.refresh_from_db()
        self.assertEqual(membership.role, "child")
        self.assertEqual(membership.display_name, "Kid")

    def test_owner_creates_invitation_and_public_info_is_readable(self):
        expires = (timezone.now() + timedelta(days=7)).isoformat()
        response = self.client.post("/api/invitations/", {"family": str(self.family.id), "role": "adult", "email": "new@example.com", "expires_at": expires}, format="json")
        self.assertEqual(response.status_code, 201)
        token = response.data["token"]
        public = APIClient().get(f"/api/invite/{token}/")
        self.assertEqual(public.status_code, 200)
        self.assertEqual(public.data["family_name"], "Alice Family")

    def test_invite_registers_user_sets_http_only_cookies_and_is_single_use(self):
        invite = FamilyInvitation.objects.create(family=self.family, role="adult", email="new@example.com", invited_by=self.alice, expires_at=timezone.now() + timedelta(days=7))
        anon = APIClient()
        response = anon.post(f"/api/invite/{invite.token}/register/", {"username": "newperson", "email": "new@example.com", "password": "very-secure-123", "display_name": "New Person"}, format="json")
        self.assertEqual(response.status_code, 201)
        self.assertNotIn("access", response.data)
        self.assertTrue(response.cookies["famuhle_access"]["httponly"])
        self.assertTrue(response.cookies["famuhle_refresh"]["httponly"])
        user = get_user_model().objects.get(username="newperson")
        self.assertTrue(Membership.objects.filter(family=self.family, user=user, role="adult").exists())
        second = APIClient().post(f"/api/invite/{invite.token}/register/", {"username": "another", "email": "new@example.com", "password": "very-secure-123"}, format="json")
        self.assertEqual(second.status_code, 400)

    def test_email_bound_invite_rejects_wrong_email(self):
        invite = FamilyInvitation.objects.create(family=self.family, role="adult", email="target@example.com", invited_by=self.alice, expires_at=timezone.now() + timedelta(days=7))
        response = APIClient().post(f"/api/invite/{invite.token}/register/", {"username": "wronguser", "email": "wrong@example.com", "password": "very-secure-123"}, format="json")
        self.assertEqual(response.status_code, 403)

    def test_cookie_login_session_refresh_and_logout(self):
        client = APIClient()
        login_response = client.post("/api/auth/login/", {"username": "alice", "password": "test-pass-123"}, format="json")
        self.assertEqual(login_response.status_code, 200)
        self.assertNotIn("access", login_response.data)
        self.assertTrue(login_response.cookies["famuhle_access"]["httponly"])
        session = client.get("/api/auth/session/")
        self.assertEqual(session.status_code, 200)
        self.assertEqual(session.data["user"]["username"], "alice")
        refresh = client.post("/api/auth/refresh/", {}, format="json")
        self.assertEqual(refresh.status_code, 200)
        logout = client.post("/api/auth/logout/", {}, format="json")
        self.assertEqual(logout.status_code, 200)

    @patch.dict(os.environ, {"VAPID_PUBLIC_KEY": "test-public", "VAPID_PRIVATE_KEY": "test-private", "VAPID_SUBJECT": "mailto:test@example.com"})
    def test_push_subscription_can_be_registered(self):
        response = self.client.post(
            "/api/push/subscribe/",
            {"endpoint": "https://push.example/subscription", "keys": {"p256dh": "p256dh", "auth": "auth"}},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(PushSubscription.objects.filter(user=self.alice, active=True).exists())

    @patch.dict(os.environ, {"VAPID_PUBLIC_KEY": "test-public", "VAPID_PRIVATE_KEY": "test-private", "VAPID_SUBJECT": "mailto:test@example.com"})
    @patch("family.push.webpush")
    def test_warning_rule_can_send_web_push(self, mocked_webpush):
        PushSubscription.objects.create(user=self.alice, endpoint="https://push.example/subscription", p256dh="p", auth="a")
        FamilyEvent.objects.create(
            family=self.family,
            type="public.warning",
            title="Amtliche Warnung",
            starts_at=timezone.now() - timedelta(minutes=1),
            ends_at=timezone.now() + timedelta(hours=1),
            payload={"severity": "Severe"},
        )
        rule = AutomationRule.objects.create(
            family=self.family,
            name="Warnung aufs Handy",
            trigger_type=AutomationRule.Trigger.WARNING_ACTIVE,
            action_type=AutomationRule.Action.PUSH_NOTIFY,
            action_config={"title": "{event_title}", "body": "Bitte prüfen", "url": "/?page=calendar"},
        )
        self.assertEqual(run_rule(rule), 1)
        mocked_webpush.assert_called_once()
        subscription = PushSubscription.objects.get(user=self.alice)
        self.assertIsNotNone(subscription.last_success_at)
