from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from family.models import Family, Membership
from .models import Expense, ExpenseBudget, get_default_expense_ledger


User = get_user_model()


class SharedFundingTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="shared-owner", password="test")
        self.other = User.objects.create_user(username="shared-adult", password="test")
        self.outsider = User.objects.create_user(username="shared-outsider", password="test")
        self.family = Family.objects.create(name="Shared Family", slug="shared-family")
        self.owner = Membership.objects.create(
            family=self.family,
            user=self.user,
            role=Membership.Role.OWNER,
            display_name="Alex",
        )
        self.adult = Membership.objects.create(
            family=self.family,
            user=self.other,
            role=Membership.Role.ADULT,
            display_name="Sam",
        )
        self.foreign_family = Family.objects.create(name="Foreign", slug="shared-foreign")
        self.foreign_member = Membership.objects.create(
            family=self.foreign_family,
            user=self.outsider,
            role=Membership.Role.OWNER,
            display_name="Foreign",
        )
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.ledger = get_default_expense_ledger(self.family)

    def _member_payload(self, amount="10.00"):
        return {
            "family": str(self.family.id),
            "total_amount": amount,
            "currency": "EUR",
            "participants": [str(self.owner.id), str(self.adult.id)],
            "split_type": "equal",
        }

    def _shared_payload(self, amount="10.00"):
        return {
            "family": str(self.family.id),
            "funding_source": Expense.FundingSource.SHARED,
            "total_amount": amount,
            "currency": "EUR",
        }

    def test_shared_expense_is_balance_neutral_but_counts_against_budget(self):
        self.ledger.budget_amount = Decimal("5.00")
        self.ledger.save(update_fields=["budget_amount", "updated_at"])

        response = self.client.post("/api/expenses/", self._shared_payload(), format="json")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["funding_source"], Expense.FundingSource.SHARED)
        self.assertIsNone(response.data["paid_by"])
        self.assertIsNone(response.data["paid_by_name"])
        self.assertEqual(response.data["shares"], [])

        expense = Expense.objects.get(id=response.data["id"])
        self.assertIsNone(expense.paid_by_id)
        self.assertFalse(expense.shares.exists())

        balance = self.client.get(f"/api/expenses/balance/?family={self.family.id}&currency=EUR")
        self.assertEqual(balance.status_code, 200, balance.data)
        self.assertEqual(Decimal(balance.data["open_amount"]), Decimal("0.00"))
        for member in balance.data["members"]:
            self.assertEqual(Decimal(member["paid"]), Decimal("0.00"))
            self.assertEqual(Decimal(member["share"]), Decimal("0.00"))
            self.assertEqual(Decimal(member["balance"]), Decimal("0.00"))

        plan = self.client.get(f"/api/expenses/settlement-plan/?family={self.family.id}&currency=EUR")
        self.assertEqual(plan.status_code, 200, plan.data)
        self.assertEqual(plan.data["transfers"], [])

        budget = self.client.get(f"/api/expense-ledgers/{self.ledger.id}/budget-summary/")
        self.assertEqual(budget.status_code, 200, budget.data)
        self.assertEqual(Decimal(budget.data["spent_amount"]), Decimal("10.00"))
        self.assertEqual(Decimal(budget.data["remaining_amount"]), Decimal("-5.00"))
        self.assertTrue(budget.data["over_budget"])

    def test_shared_expense_can_be_budget_allocated(self):
        budget = ExpenseBudget.objects.create(
            family=self.family,
            ledger=self.ledger,
            name="Haushalt",
            amount="20.00",
        )
        created = self.client.post("/api/expenses/", self._shared_payload("7.50"), format="json")
        self.assertEqual(created.status_code, 201, created.data)

        allocated = self.client.put(
            f"/api/expenses/{created.data['id']}/budget-allocations/",
            {
                "allocations": [
                    {
                        "budget": str(budget.id),
                        "amount_in_budget_currency": "7.50",
                    }
                ]
            },
            format="json",
        )
        self.assertEqual(allocated.status_code, 200, allocated.data)
        self.assertEqual(allocated.data["allocations"][0]["budget"], str(budget.id))
        self.assertEqual(
            Decimal(allocated.data["allocations"][0]["amount_in_budget_currency"]),
            Decimal("7.50"),
        )

    def test_shared_rejects_personal_payer_and_debt_split(self):
        with_payer = self.client.post(
            "/api/expenses/",
            {**self._shared_payload(), "paid_by": str(self.owner.id)},
            format="json",
        )
        self.assertEqual(with_payer.status_code, 400, with_payer.data)
        self.assertIn("paid_by", with_payer.data)

        with_foreign_payer = self.client.post(
            "/api/expenses/",
            {**self._shared_payload(), "paid_by": str(self.foreign_member.id)},
            format="json",
        )
        self.assertEqual(with_foreign_payer.status_code, 400, with_foreign_payer.data)
        self.assertIn("paid_by", with_foreign_payer.data)

        with_participants = self.client.post(
            "/api/expenses/",
            {
                **self._shared_payload(),
                "participants": [str(self.owner.id), str(self.adult.id)],
            },
            format="json",
        )
        self.assertEqual(with_participants.status_code, 400, with_participants.data)
        self.assertIn("participants", with_participants.data)

    def test_legacy_member_default_keeps_existing_balance_semantics(self):
        response = self.client.post("/api/expenses/", self._member_payload(), format="json")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["funding_source"], Expense.FundingSource.MEMBER)
        self.assertEqual(str(response.data["paid_by"]), str(self.owner.id))
        self.assertEqual(len(response.data["shares"]), 2)

        balance = self.client.get(f"/api/expenses/balance/?family={self.family.id}&currency=EUR")
        rows = {row["name"]: Decimal(row["balance"]) for row in balance.data["members"]}
        self.assertEqual(rows["Alex"], Decimal("5.00"))
        self.assertEqual(rows["Sam"], Decimal("-5.00"))

    def test_switch_member_to_shared_clears_debt_and_switch_back_requires_split(self):
        created = self.client.post("/api/expenses/", self._member_payload(), format="json")
        self.assertEqual(created.status_code, 201, created.data)
        expense_id = created.data["id"]

        shared = self.client.patch(
            f"/api/expenses/{expense_id}/",
            {"funding_source": Expense.FundingSource.SHARED},
            format="json",
        )
        self.assertEqual(shared.status_code, 200, shared.data)
        self.assertIsNone(shared.data["paid_by"])
        self.assertEqual(shared.data["shares"], [])

        balance = self.client.get(f"/api/expenses/balance/?family={self.family.id}&currency=EUR")
        self.assertTrue(all(Decimal(row["balance"]) == Decimal("0.00") for row in balance.data["members"]))

        invalid_member = self.client.patch(
            f"/api/expenses/{expense_id}/",
            {"funding_source": Expense.FundingSource.MEMBER},
            format="json",
        )
        self.assertEqual(invalid_member.status_code, 400, invalid_member.data)
        self.assertIn("participants", invalid_member.data)

        member = self.client.patch(
            f"/api/expenses/{expense_id}/",
            {
                "funding_source": Expense.FundingSource.MEMBER,
                "participants": [str(self.owner.id), str(self.adult.id)],
                "split_type": "equal",
            },
            format="json",
        )
        self.assertEqual(member.status_code, 200, member.data)
        self.assertEqual(str(member.data["paid_by"]), str(self.owner.id))
        self.assertEqual(len(member.data["shares"]), 2)

        balance = self.client.get(f"/api/expenses/balance/?family={self.family.id}&currency=EUR")
        rows = {row["name"]: Decimal(row["balance"]) for row in balance.data["members"]}
        self.assertEqual(rows["Alex"], Decimal("5.00"))
        self.assertEqual(rows["Sam"], Decimal("-5.00"))
