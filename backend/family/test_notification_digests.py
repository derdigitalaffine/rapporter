from datetime import datetime, timedelta, timezone as dt_timezone
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient
from .domain_notifications import notify_domain_event
from .models import Family, Membership, ShoppingItem, ShoppingList
from .models_features import NotificationBatch, NotificationPreference
from .notification_digests import delivery_policy, flush_notification_batches, is_quiet

class NotificationDigestTests(TestCase):
    def setUp(self):
        self.actor = get_user_model().objects.create_user(username="digest-actor")
        self.user = get_user_model().objects.create_user(username="digest-recipient")
        self.family = Family.objects.create(name="Home", slug="digest-home")
        Membership.objects.create(family=self.family, user=self.actor)
        self.member = Membership.objects.create(family=self.family, user=self.user)
        self.shopping = ShoppingList.objects.create(family=self.family, name="REWE")
        self.pref = NotificationPreference.objects.create(membership=self.member)
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def event(self, name="Milk", kind="created", item=None):
        item = item or ShoppingItem.objects.create(shopping_list=self.shopping, name=name)
        notify_domain_event(self.family, f"shopping.item.{kind}", actor=self.actor, context={"list": self.shopping.name, "list_id": self.shopping.id, "item_id": item.id, "item": name})
        return item

    def flush(self):
        return flush_notification_batches(now=timezone.now() + timedelta(minutes=3))

    @patch("family.notification_digests.send_user_push", return_value={"sent": 1, "errors": 0})
    @patch("family.domain_notifications.send_user_push")
    def test_burst_is_one_digest_and_not_sent_twice(self, immediate, sender):
        for name in ["Milk", "Bread", "Apples", "Tea"]: self.event(name)
        immediate.assert_not_called()
        self.assertEqual(NotificationBatch.objects.count(), 1)
        self.flush(); self.flush()
        sender.assert_called_once()
        self.assertEqual(sender.call_args.args[0], self.user)
        self.assertIn("4 Änderungen", sender.call_args.args[1])
        self.assertIn("Milk, Bread, Apples …", sender.call_args.args[2])
        self.assertNotIn("item=", sender.call_args.args[3])
        self.assertEqual(NotificationBatch.objects.get().events, {})

    @patch("family.notification_digests.send_user_push")
    def test_check_undo_cancels(self, sender):
        item = ShoppingItem.objects.create(shopping_list=self.shopping, name="Milk")
        self.event(kind="completed", item=item); self.event(kind="reopened", item=item)
        self.flush(); sender.assert_not_called()

    @patch("family.notification_digests.send_user_push")
    def test_preferences_rechecked(self, sender):
        self.event(); self.pref.shopping = False; self.pref.save(); self.flush()
        sender.assert_not_called(); self.assertEqual(NotificationBatch.objects.count(), 0)

    @patch("family.notification_digests.send_user_push")
    def test_deleted_membership_cascades_outbox(self, sender):
        self.event(); self.member.delete(); self.flush()
        sender.assert_not_called(); self.assertEqual(NotificationBatch.objects.count(), 0)

    @patch("family.domain_notifications.send_user_push", return_value={"sent": 1, "errors": 0})
    def test_modes_and_targeted_assignment(self, sender):
        self.pref.detail_level = "important"; self.pref.save(); self.event()
        self.assertEqual(NotificationBatch.objects.count(), 0)
        notify_domain_event(self.family, "task.assigned", actor=self.actor, context={"item": "Bins"}, target_users=[self.user])
        sender.assert_called_once()
        self.pref.detail_level = "all"; self.pref.save(); self.event("Bread")
        self.assertEqual(sender.call_count, 2)

    def test_quiet_hours_timezone_and_validation(self):
        self.client.patch(f"/api/push/preferences/?family={self.family.pk}", {"quiet_hours_enabled": True, "quiet_start": "22:00", "quiet_end": "07:00"}, format="json")
        self.pref.refresh_from_db()
        now = datetime(2026, 10, 9, 21, 0, tzinfo=dt_timezone.utc)
        self.assertTrue(is_quiet(self.pref, self.family, now))
        self.assertFalse(is_quiet(self.pref, self.family, now + timedelta(hours=9)))
        self.assertEqual(delivery_policy(self.pref, self.family, "task.assigned", now), "queue")
        bad = self.client.patch(f"/api/push/preferences/?family={self.family.pk}", {"quiet_start": "07:00"}, format="json")
        self.assertEqual(bad.status_code, 400)
        invalid = self.client.patch(f"/api/push/preferences/?family={self.family.pk}", {"detail_level": "spam"}, format="json")
        self.assertEqual(invalid.status_code, 400)

    @patch("family.notification_digests.send_user_push", side_effect=[{"sent": 0, "errors": 1}, {"sent": 1, "errors": 0}])
    def test_retry_persistent_and_stable_tag(self, sender):
        self.event(); now = timezone.now() + timedelta(minutes=3)
        flush_notification_batches(now)
        batch = NotificationBatch.objects.get()
        self.assertEqual(batch.attempts, 1); self.assertIsNone(batch.delivered_at)
        flush_notification_batches(now + timedelta(minutes=1)); self.assertEqual(sender.call_count, 1)
        flush_notification_batches(now + timedelta(minutes=3)); self.assertEqual(sender.call_count, 2)
        self.assertEqual(sender.call_args_list[0].kwargs["tag"], sender.call_args_list[1].kwargs["tag"])

    @patch("family.notification_digests.send_user_push", return_value={"sent": 1, "errors": 0})
    def test_english_separate_lists_fixed_window(self, sender):
        self.family.locale = "en"; self.family.save(); self.event()
        due = NotificationBatch.objects.get().due_at
        self.event("Bread"); self.assertEqual(NotificationBatch.objects.get().due_at, due)
        self.shopping = ShoppingList.objects.create(family=self.family, name="ALDI"); self.event("Tea")
        self.assertEqual(NotificationBatch.objects.count(), 2)
        self.flush(); self.assertEqual(sender.call_count, 2)
        self.assertIn("changes", sender.call_args_list[0].args[1])

    @patch("family.notification_digests.send_user_push", side_effect=RuntimeError("Network unavailable"))
    def test_failure_retry_bounded(self, sender):
        self.event(); now = timezone.now()
        for attempt in range(5): flush_notification_batches(now + timedelta(hours=attempt + 1))
        self.assertEqual(NotificationBatch.objects.get().attempts, 5)
        self.assertIsNotNone(NotificationBatch.objects.get().delivered_at)

    @patch("family.notification_digests.send_user_push")
    def test_withdrawn_targeted_message_does_not_leak_after_quiet_hours(self, sender):
        from .models import InboxItem, InboxReceipt
        from .notification_digests import enqueue_notification
        item = InboxItem.objects.create(family=self.family, title="Private", body="Secret", source="manual_message", created_by=self.actor)
        InboxReceipt.objects.create(item=item, membership=self.member)
        enqueue_notification(self.member, "inbox.created", {"inbox_id": item.pk, "item": item.title, "actor": "Sender"})
        item.withdrawn_at = timezone.now(); item.save()
        self.flush(); sender.assert_not_called()

    @patch("family.notification_digests.MAX_EVENTS", 2)
    @patch("family.notification_digests.send_user_push", return_value={"sent": 1, "errors": 0})
    def test_large_burst_is_bounded_and_deleted_list_not_delivered(self, sender):
        for i in range(5): self.event(f"Item {i}")
        self.assertEqual(len(NotificationBatch.objects.get().events), 3)
        self.flush()
        self.assertIn("2+ Änderungen", sender.call_args.args[1])
        sender.reset_mock()
        for i in range(5): self.event(f"New item {i}")
        self.shopping.delete(); self.flush()
        sender.assert_not_called()

from concurrent.futures import ThreadPoolExecutor
from unittest import skipUnless
from django.db import connection, close_old_connections
from django.test import TransactionTestCase

@skipUnless(connection.vendor == "postgresql", "Requires PostgreSQL row locking")
class NotificationConcurrencyTests(TransactionTestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="concurrent-recipient")
        self.family = Family.objects.create(name="Concurrent", slug="concurrent")
        self.member = Membership.objects.create(user=self.user, family=self.family)
        self.shopping = ShoppingList.objects.create(family=self.family, name="REWE")
        self.items = [ShoppingItem.objects.create(shopping_list=self.shopping, name=f"Item {i}") for i in range(2)]
    def isolated(self, callback):
        close_old_connections()
        try: return callback()
        finally: close_old_connections()
    @patch("family.notification_digests.send_user_push", return_value={"sent": 1, "errors": 0})
    def test_parallel_writers_then_parallel_schedulers(self, sender):
        from .notification_digests import enqueue_notification
        def enqueue(item):
            return self.isolated(lambda: enqueue_notification(self.member, "shopping.item.created", {"item_id": item.id, "list_id": self.shopping.id, "list": "REWE", "item": item.name}))
        with ThreadPoolExecutor(max_workers=2) as executor: list(executor.map(enqueue, self.items))
        self.assertEqual(len(NotificationBatch.objects.get().events), 2)
        now = timezone.now() + timedelta(minutes=3)
        with ThreadPoolExecutor(max_workers=2) as executor:
            list(executor.map(lambda _: self.isolated(lambda: flush_notification_batches(now)), range(2)))
        sender.assert_called_once()
