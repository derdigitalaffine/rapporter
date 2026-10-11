from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from family.domain_notifications import notify_domain_event
from family.models import Family, Membership
from family.models_features import NotificationBadgeState, NotificationPreference

from .models import Notification
from .services import normalize_resource_url, record_notification


class NotificationApiTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user(username="notify-owner", password="pw")
        self.member = User.objects.create_user(username="notify-member", password="pw")
        self.outsider = User.objects.create_user(username="notify-outsider", password="pw")
        self.family = Family.objects.create(name="Notify", slug="notify-family")
        self.other_family = Family.objects.create(name="Other", slug="notify-other")
        self.owner_membership = Membership.objects.create(
            family=self.family, user=self.owner, role=Membership.Role.OWNER, display_name="Owner"
        )
        self.member_membership = Membership.objects.create(
            family=self.family, user=self.member, role=Membership.Role.ADULT, display_name="Member"
        )
        self.outsider_membership = Membership.objects.create(
            family=self.other_family, user=self.outsider, role=Membership.Role.OWNER, display_name="Outsider"
        )
        self.client = APIClient()
        self.client.force_authenticate(self.member)

    def create_notification(self, **overrides):
        values = {
            "recipient": self.member_membership,
            "event_type": "task.created",
            "title": "Neue Aufgabe",
            "body": "Milch holen",
            "resource_url": "/?page=tasks&task=123",
        }
        values.update(overrides)
        row, _ = record_notification(**values)
        return row

    def test_internal_resource_links_are_normalized_and_external_links_rejected(self):
        self.assertEqual(normalize_resource_url("/?page=tasks&task=123#section"), "/?page=tasks&task=123")
        with self.assertRaisesMessage(ValueError, "invalid_resource_url"):
            normalize_resource_url("https://evil.example/phish")
        with self.assertRaisesMessage(ValueError, "invalid_resource_url"):
            normalize_resource_url("//evil.example/phish")
        with self.assertRaisesMessage(ValueError, "invalid_resource_url"):
            normalize_resource_url("/safe\\evil")

    def test_collection_is_membership_scoped_and_cross_family_fails_closed(self):
        own = self.create_notification()
        record_notification(
            recipient=self.outsider_membership,
            event_type="calendar.event.created",
            title="Private",
            resource_url="/?page=calendar",
        )
        response = self.client.get(f"/api/notifications/?family={self.family.id}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual([item["id"] for item in response.data["results"]], [str(own.id)])
        self.assertEqual(response.data["unread_count"], 1)
        foreign = self.client.get(f"/api/notifications/?family={self.other_family.id}")
        self.assertEqual(foreign.status_code, 404)
        detail = self.client.patch(
            f"/api/notifications/{Notification.objects.get(recipient=self.outsider_membership).id}/",
            {"read": True},
            format="json",
        )
        self.assertEqual(detail.status_code, 404)

        self.family.status = Family.Status.SUSPENDED
        self.family.save(update_fields=["status", "updated_at"])
        self.assertEqual(self.client.get(f"/api/notifications/?family={self.family.id}").status_code, 404)
        self.assertEqual(self.client.patch(f"/api/notifications/{own.id}/", {"read": True}, format="json").status_code, 404)

    def test_read_state_is_idempotent_and_launcher_badge_is_only_a_derived_mirror(self):
        first = self.create_notification()
        second = self.create_notification(title="Zweite Aufgabe")
        state = NotificationBadgeState.objects.get(user=self.member)
        self.assertEqual(state.unread_count, 2)

        read = self.client.patch(f"/api/notifications/{first.id}/", {"read": True}, format="json")
        self.assertEqual(read.status_code, 200)
        self.assertTrue(read.data["read"])
        first_read_at = Notification.objects.get(pk=first.id).read_at
        repeated = self.client.patch(f"/api/notifications/{first.id}/", {"read": True}, format="json")
        self.assertEqual(repeated.status_code, 200)
        self.assertEqual(Notification.objects.get(pk=first.id).read_at, first_read_at)
        self.assertEqual(NotificationBadgeState.objects.get(user=self.member).unread_count, 1)

        all_read = self.client.post("/api/notifications/read-all/", {"family": str(self.family.id)}, format="json")
        self.assertEqual(all_read.status_code, 200)
        self.assertEqual(all_read.data, {"updated": 1, "unread_count": 0})
        self.assertFalse(Notification.objects.filter(recipient=self.member_membership, read_at__isnull=True).exists())
        self.assertEqual(NotificationBadgeState.objects.get(user=self.member).unread_count, 0)
        self.assertIsNotNone(Notification.objects.get(pk=second.id).read_at)

    def test_cursor_pagination_has_stable_non_overlapping_pages(self):
        rows = [self.create_notification(title=f"N{i}") for i in range(4)]
        base = timezone.now()
        for index, row in enumerate(rows):
            Notification.objects.filter(pk=row.pk).update(created_at=base - timedelta(minutes=index))
        first = self.client.get(f"/api/notifications/?family={self.family.id}&limit=2")
        self.assertEqual(first.status_code, 200)
        self.assertEqual(len(first.data["results"]), 2)
        self.assertTrue(first.data["next_cursor"])
        second = self.client.get(
            f"/api/notifications/?family={self.family.id}&limit=2&cursor={first.data['next_cursor']}"
        )
        self.assertEqual(second.status_code, 200)
        first_ids = {row["id"] for row in first.data["results"]}
        second_ids = {row["id"] for row in second.data["results"]}
        self.assertFalse(first_ids & second_ids)
        self.assertEqual(first_ids | second_ids, {str(row.id) for row in rows})

    def test_domain_events_create_in_app_rows_even_when_push_channel_is_disabled(self):
        preference, _ = NotificationPreference.objects.get_or_create(membership=self.member_membership)
        preference.tasks = False
        preference.save(update_fields=["tasks", "updated_at"])
        result = notify_domain_event(
            self.family,
            "task.created",
            actor=self.owner,
            context={"item": "Müll rausbringen", "list": "Haushalt", "task_id": "11111111-1111-1111-1111-111111111111"},
            url="/?page=tasks&task=11111111-1111-1111-1111-111111111111",
        )
        self.assertEqual(result["recipients"], 0)
        notification = Notification.objects.get(recipient=self.member_membership)
        self.assertEqual(notification.event_type, "task.created")
        self.assertEqual(notification.title, "Neue Aufgabe")
        self.assertEqual(notification.resource_url, "/?page=tasks&task=11111111-1111-1111-1111-111111111111")
        self.assertFalse(Notification.objects.filter(recipient=self.owner_membership).exists())
        preference.refresh_from_db()
        self.assertFalse(preference.tasks)
