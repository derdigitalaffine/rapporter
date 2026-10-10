import json
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from .domain_notifications import notify_domain_event
from .models import Family, Membership
from .models_features import NotificationBadgeState
from .push import send_to_subscription


class NotificationBadgeTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.actor = User.objects.create_user(username="badge-actor")
        self.user = User.objects.create_user(username="badge-recipient")
        self.family = Family.objects.create(name="Badge Family", slug="badge-family")
        Membership.objects.create(family=self.family, user=self.actor, role=Membership.Role.OWNER)
        Membership.objects.create(family=self.family, user=self.user, role=Membership.Role.ADULT)
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    @patch("family.domain_notifications.send_user_push", return_value={"sent": 1, "errors": 0})
    def test_relevant_events_increment_account_badge_and_push_current_count(self, sender):
        notify_domain_event(
            self.family,
            "calendar.event.created",
            actor=self.actor,
            context={"item": "Kinderarzt", "event_id": "event-1"},
        )
        notify_domain_event(
            self.family,
            "calendar.event.updated",
            actor=self.actor,
            context={"item": "Kinderarzt", "event_id": "event-1"},
        )
        self.assertEqual(NotificationBadgeState.objects.get(user=self.user).unread_count, 2)
        self.assertEqual(sender.call_args_list[0].kwargs["badge_count"], 1)
        self.assertEqual(sender.call_args_list[1].kwargs["badge_count"], 2)

    @patch("family.domain_notifications.send_user_push", return_value={"sent": 1, "errors": 0})
    def test_actor_does_not_count_own_event_but_other_members_do(self, sender):
        notify_domain_event(
            self.family,
            "calendar.event.created",
            actor=self.user,
            context={"item": "Eigener Termin", "event_id": "event-2"},
        )
        self.assertFalse(NotificationBadgeState.objects.filter(user=self.user).exists())
        self.assertTrue(NotificationBadgeState.objects.filter(user=self.actor).exists())
        self.assertEqual(sender.call_count, 1)
        self.assertEqual(sender.call_args.args[0], self.actor)

    def test_badge_endpoint_reads_and_acknowledges_all_unread_activity(self):
        NotificationBadgeState.objects.create(user=self.user, unread_count=4)
        response = self.client.get("/api/push/badge/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["unread_count"], 4)
        response = self.client.post("/api/push/badge/", {}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["unread_count"], 0)
        self.assertEqual(NotificationBadgeState.objects.get(user=self.user).unread_count, 0)

    def test_badge_endpoint_requires_authentication(self):
        self.client.force_authenticate(None)
        self.assertIn(self.client.get("/api/push/badge/").status_code, (401, 403))
        self.assertIn(self.client.post("/api/push/badge/", {}, format="json").status_code, (401, 403))

    @patch("family.push.webpush")
    @patch.dict("os.environ", {"VAPID_PUBLIC_KEY": "public", "VAPID_PRIVATE_KEY": "private"}, clear=False)
    def test_web_push_payload_contains_numeric_badge_count(self, webpush):
        from .models import PushSubscription

        subscription = PushSubscription.objects.create(
            user=self.user,
            endpoint="https://push.example.test/subscription",
            p256dh="p256dh",
            auth="auth",
        )
        send_to_subscription(subscription, "Termin", "Neu", "/?page=calendar", badge_count=7)
        payload = json.loads(webpush.call_args.kwargs["data"])
        self.assertEqual(payload["badge_count"], 7)
