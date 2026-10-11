from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from .models import Family, Membership
from .models_features import LoyaltyCard
from .pass_catalog import PASS_ICON_KEYS


class PassCoreTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user(username="pass-owner", password="test-pass-123")
        self.shared = User.objects.create_user(username="pass-shared", password="test-pass-123")
        self.private = User.objects.create_user(username="pass-private", password="test-pass-123")
        self.outsider = User.objects.create_user(username="pass-outsider", password="test-pass-123")
        self.family = Family.objects.create(name="Pass Family", slug="pass-family")
        self.other = Family.objects.create(name="Other Pass Family", slug="other-pass-family")
        self.owner_member = Membership.objects.create(family=self.family, user=self.owner, role=Membership.Role.OWNER)
        self.shared_member = Membership.objects.create(family=self.family, user=self.shared, role=Membership.Role.ADULT)
        self.private_member = Membership.objects.create(family=self.family, user=self.private, role=Membership.Role.TEEN)
        Membership.objects.create(family=self.other, user=self.outsider, role=Membership.Role.OWNER)
        self.client = APIClient()
        self.client.force_authenticate(self.owner)

    def rows(self, response):
        data = response.data
        return data.get("results", data) if hasattr(data, "get") else data

    def create_pass(self, **overrides):
        payload = {
            "family": str(self.family.id),
            "name": "10 € Gutschein",
            "pass_type": "voucher",
            "icon_key": "gift",
            "color": "#6750A4",
            "color_mode": "auto",
            "barcode_value": "VOUCHER-123",
            "barcode_format": "code128",
            "undo_window_minutes": 10,
            "shared_with_ids": [str(self.shared_member.id)],
        }
        payload.update(overrides)
        return self.client.post("/api/loyalty-cards/", payload, format="json")

    def test_existing_loyalty_contract_defaults_without_barcode_rewrite(self):
        card = LoyaltyCard.objects.create(
            family=self.family,
            name="Legacy PAYBACK",
            logo="★",
            color="#003B7A",
            barcode_value="001122334455",
            barcode_format=LoyaltyCard.BarcodeFormat.CODE128,
            created_by=self.owner,
        )
        self.assertEqual(card.pass_type, LoyaltyCard.PassType.LOYALTY_CARD)
        self.assertEqual(card.logo, "★")
        self.assertEqual(card.color, "#003B7A")
        response = self.client.patch(
            f"/api/loyalty-cards/{card.id}/",
            {"favorite": True, "logo": "★"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        card.refresh_from_db()
        self.assertEqual(card.barcode_value, "001122334455")
        self.assertEqual(card.barcode_format, LoyaltyCard.BarcodeFormat.CODE128)

    def test_registry_is_fixed_large_and_rejects_arbitrary_icon_or_color(self):
        self.assertGreaterEqual(len(PASS_ICON_KEYS), 50)
        catalog = self.client.get("/api/loyalty-cards/catalog/")
        self.assertEqual(catalog.status_code, 200)
        self.assertGreaterEqual(len(catalog.data["icons"]), 50)
        self.assertEqual(len({row["key"] for row in catalog.data["icons"]}), len(catalog.data["icons"]))
        bad_icon = self.create_pass(icon_key="evil <script>")
        self.assertEqual(bad_icon.status_code, 400)
        bad_color = self.create_pass(color="red; background:url(x)")
        self.assertEqual(bad_color.status_code, 400)
        arbitrary_legacy_logo = self.create_pass(logo="some-css-class")
        self.assertEqual(arbitrary_legacy_logo.status_code, 400)

    def test_voucher_auto_branding_and_acl_reuse_existing_sharing(self):
        response = self.create_pass()
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["pass_type"], "voucher")
        self.assertEqual(response.data["icon_key"], "gift")
        self.assertRegex(response.data["resolved_color"], r"^#[0-9A-Fa-f]{6}$")
        card_id = response.data["id"]

        self.client.force_authenticate(self.shared)
        visible = self.client.get(f"/api/loyalty-cards/{card_id}/")
        self.assertEqual(visible.status_code, 200)
        self.assertEqual(visible.data["barcode_value"], "VOUCHER-123")
        self.client.force_authenticate(self.private)
        self.assertEqual(self.client.get(f"/api/loyalty-cards/{card_id}/").status_code, 404)
        self.client.force_authenticate(self.outsider)
        self.assertEqual(self.client.get(f"/api/loyalty-cards/{card_id}/").status_code, 404)

    def test_shared_member_can_redeem_and_undo_within_grace_period(self):
        created = self.create_pass()
        card_id = created.data["id"]
        self.client.force_authenticate(self.shared)
        used = self.client.post(f"/api/loyalty-cards/{card_id}/redeem/", {}, format="json")
        self.assertEqual(used.status_code, 200)
        self.assertEqual(used.data["lifecycle_status"], "used")
        self.assertTrue(used.data["can_restore"])
        self.assertEqual(len(self.rows(self.client.get(f"/api/loyalty-cards/sync/?family={self.family.id}"))), 0)

        restored = self.client.post(f"/api/loyalty-cards/{card_id}/restore/", {}, format="json")
        self.assertEqual(restored.status_code, 200)
        self.assertEqual(restored.data["lifecycle_status"], "active")
        self.assertFalse(restored.data["archived"])
        self.assertEqual(len(self.rows(self.client.get(f"/api/loyalty-cards/sync/?family={self.family.id}"))), 1)

    def test_restore_is_rejected_after_grace_period(self):
        created = self.create_pass(undo_window_minutes=1)
        card_id = created.data["id"]
        self.client.force_authenticate(self.shared)
        self.assertEqual(self.client.post(f"/api/loyalty-cards/{card_id}/redeem/", {}, format="json").status_code, 200)
        LoyaltyCard.objects.filter(pk=card_id).update(restore_until=timezone.now() - timedelta(seconds=1))
        expired = self.client.post(f"/api/loyalty-cards/{card_id}/restore/", {}, format="json")
        self.assertEqual(expired.status_code, 409)
        card = LoyaltyCard.objects.get(pk=card_id)
        self.assertTrue(card.archived)
        self.assertEqual(card.archive_reason, LoyaltyCard.ArchiveReason.USED)

    def test_event_bound_ticket_archives_automatically_without_ui_restore(self):
        ticket = LoyaltyCard.objects.create(
            family=self.family,
            name="Museum 14:00",
            pass_type=LoyaltyCard.PassType.TICKET,
            icon_key="museum",
            barcode_value="TICKET-42",
            barcode_format=LoyaltyCard.BarcodeFormat.QR,
            event_ends_at=timezone.now() - timedelta(minutes=1),
            created_by=self.owner,
        )
        ticket.shared_with.add(self.shared_member)
        response = self.client.get(f"/api/loyalty-cards/sync/?family={self.family.id}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(self.rows(response)), 0)
        ticket.refresh_from_db()
        self.assertTrue(ticket.archived)
        self.assertEqual(ticket.archive_reason, LoyaltyCard.ArchiveReason.EVENT_ENDED)
        self.assertIsNone(ticket.restore_until)
        restore = self.client.post(f"/api/loyalty-cards/{ticket.id}/restore/", {}, format="json")
        self.assertEqual(restore.status_code, 409)

    def test_manual_archive_has_no_undo_window(self):
        created = self.create_pass(pass_type="coupon", icon_key="coupon")
        card_id = created.data["id"]
        deleted = self.client.delete(f"/api/loyalty-cards/{card_id}/")
        self.assertEqual(deleted.status_code, 204)
        card = LoyaltyCard.objects.get(pk=card_id)
        self.assertTrue(card.archived)
        self.assertEqual(card.archive_reason, LoyaltyCard.ArchiveReason.MANUAL)
        self.assertIsNone(card.restore_until)
