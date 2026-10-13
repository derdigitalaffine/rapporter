from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from family.models import Family, Membership
from .models import Expense, ExpenseLedger

User = get_user_model()


class ExpenseLedgerSplitDefaultTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="split-alex", password="test")
        self.other = User.objects.create_user(username="split-sam", password="test")
        self.foreign_user = User.objects.create_user(username="split-pat", password="test")
        self.family = Family.objects.create(name="Split Familie", slug="split-familie")
        self.foreign_family = Family.objects.create(name="Fremde Split Familie", slug="fremde-split-familie")
        self.alex = Membership.objects.create(family=self.family, user=self.user, role=Membership.Role.OWNER, display_name="Alex")
        self.sam = Membership.objects.create(family=self.family, user=self.other, role=Membership.Role.ADULT, display_name="Sam")
        self.pat = Membership.objects.create(family=self.foreign_family, user=self.foreign_user, role=Membership.Role.OWNER, display_name="Pat")
        self.ledger = ExpenseLedger.objects.create(family=self.family, name="Haushalt", base_currency="EUR")
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_percentage_defaults_are_persisted_and_applied_to_new_expense(self):
        response = self.client.patch(
            f"/api/expense-ledgers/{self.ledger.id}/",
            {
                "default_split_type": "percentage",
                "default_participants": [str(self.alex.id), str(self.sam.id)],
                "default_split_values": {str(self.alex.id): "60", str(self.sam.id): "40"},
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["default_split_type"], "percentage")

        created = self.client.post(
            "/api/expenses/",
            {
                "family": str(self.family.id),
                "ledger": str(self.ledger.id),
                "title": "Wochenmarkt",
                "total_amount": "25.00",
                "currency": "EUR",
            },
            format="json",
        )
        self.assertEqual(created.status_code, 201, created.data)
        expense = Expense.objects.get(id=created.data["id"])
        shares = {str(share.member_id): share for share in expense.shares.all()}
        self.assertEqual(shares[str(self.alex.id)].amount, Decimal("15.00"))
        self.assertEqual(shares[str(self.sam.id)].amount, Decimal("10.00"))
        self.assertEqual(shares[str(self.alex.id)].split_type, "percentage")
        self.assertEqual(shares[str(self.alex.id)].split_value, Decimal("60.0000"))

    def test_share_defaults_are_applied_with_cent_accurate_apportionment(self):
        self.ledger.default_split_type = "shares"
        self.ledger.default_participants = [str(self.alex.id), str(self.sam.id)]
        self.ledger.default_split_values = {str(self.alex.id): "2", str(self.sam.id): "1"}
        self.ledger.save(update_fields=["default_split_type", "default_participants", "default_split_values", "updated_at"])

        created = self.client.post(
            "/api/expenses/",
            {
                "family": str(self.family.id),
                "ledger": str(self.ledger.id),
                "title": "Drittel",
                "total_amount": "10.00",
                "currency": "EUR",
            },
            format="json",
        )
        self.assertEqual(created.status_code, 201, created.data)
        expense = Expense.objects.get(id=created.data["id"])
        amounts = sorted(share.amount for share in expense.shares.all())
        self.assertEqual(amounts, [Decimal("3.33"), Decimal("6.67")])
        self.assertEqual(sum(amounts), Decimal("10.00"))

    def test_percentage_defaults_must_total_one_hundred(self):
        response = self.client.patch(
            f"/api/expense-ledgers/{self.ledger.id}/",
            {
                "default_split_type": "percentage",
                "default_participants": [str(self.alex.id), str(self.sam.id)],
                "default_split_values": {str(self.alex.id): "70", str(self.sam.id): "20"},
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400, response.data)
        self.assertIn("default_split_values", response.data)

    def test_cross_family_default_participant_is_rejected(self):
        response = self.client.patch(
            f"/api/expense-ledgers/{self.ledger.id}/",
            {
                "default_split_type": "equal",
                "default_participants": [str(self.alex.id), str(self.pat.id)],
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400, response.data)
        self.assertIn("default_participants", response.data)

    def test_empty_equal_participants_tracks_all_current_family_members(self):
        self.ledger.default_split_type = "equal"
        self.ledger.default_participants = []
        self.ledger.default_split_values = {}
        self.ledger.save(update_fields=["default_split_type", "default_participants", "default_split_values", "updated_at"])

        created = self.client.post(
            "/api/expenses/",
            {
                "family": str(self.family.id),
                "ledger": str(self.ledger.id),
                "title": "Alle",
                "total_amount": "9.00",
                "currency": "EUR",
            },
            format="json",
        )
        self.assertEqual(created.status_code, 201, created.data)
        expense = Expense.objects.get(id=created.data["id"])
        self.assertEqual(expense.shares.count(), 2)
        self.assertEqual(sum(share.amount for share in expense.shares.all()), Decimal("9.00"))
