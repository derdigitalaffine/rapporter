from decimal import Decimal
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from family.models import Family, Membership
from .models import Expense, ExpenseBudget, ExpenseShare, Settlement, get_default_expense_ledger
from .participant_models import ExpenseBudgetParticipantPlan


User = get_user_model()


class BudgetParticipantPlanTests(TestCase):
    def setUp(self):
        self.owner_user = User.objects.create_user(username="participant-owner", password="test")
        self.adult_user = User.objects.create_user(username="participant-adult", password="test")
        self.teen_user = User.objects.create_user(username="participant-teen", password="test")
        self.family = Family.objects.create(name="Planungsfamilie", slug="participant-family")
        self.owner = Membership.objects.create(
            family=self.family,
            user=self.owner_user,
            role=Membership.Role.OWNER,
            display_name="Alex",
        )
        self.adult = Membership.objects.create(
            family=self.family,
            user=self.adult_user,
            role=Membership.Role.ADULT,
            display_name="Sam",
        )
        self.teen = Membership.objects.create(
            family=self.family,
            user=self.teen_user,
            role=Membership.Role.TEEN,
            display_name="Robin",
        )
        self.foreign_user = User.objects.create_user(username="participant-foreign", password="test")
        self.foreign_family = Family.objects.create(name="Fremdfamilie", slug="participant-foreign-family")
        self.foreign_member = Membership.objects.create(
            family=self.foreign_family,
            user=self.foreign_user,
            role=Membership.Role.OWNER,
            display_name="Fremd",
        )
        self.ledger = get_default_expense_ledger(self.family)
        self.client = APIClient()
        self.client.force_authenticate(self.owner_user)

    def create_budget(self, **extra):
        payload = {
            "family": str(self.family.id),
            "ledger": str(self.ledger.id),
            "name": "Urlaub",
            "amount": "600.00",
            "client_request_id": str(uuid4()),
            **extra,
        }
        response = self.client.post("/api/expense-budgets/", payload, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        return response

    def test_owner_creates_budget_and_participant_plans_atomically_without_accounting_facts(self):
        response = self.create_budget(
            participant_plans=[
                {"member": str(self.owner.id), "spending_limit": "200,50", "planned_share": "300.00"},
                {"member": str(self.adult.id), "planned_share": "300.00"},
            ]
        )
        budget = ExpenseBudget.objects.get(id=response.data["id"])
        rows = {str(row.member_id): row for row in budget.participant_plans.all()}
        self.assertEqual(rows[str(self.owner.id)].ledger_id, self.ledger.id)
        self.assertEqual(rows[str(self.owner.id)].spending_limit, Decimal("200.50"))
        self.assertEqual(rows[str(self.owner.id)].planned_share, Decimal("300.00"))
        self.assertIsNone(rows[str(self.adult.id)].spending_limit)
        self.assertEqual(rows[str(self.adult.id)].planned_share, Decimal("300.00"))
        self.assertEqual(Expense.objects.count(), 0)
        self.assertEqual(ExpenseShare.objects.count(), 0)
        self.assertEqual(Settlement.objects.count(), 0)

    def test_overall_ledger_budget_and_participant_plan_commit_atomically(self):
        response = self.client.patch(
            f"/api/expense-ledgers/{self.ledger.id}/participant-plans/",
            {
                "family": str(self.family.id),
                "budget_amount": "900,50",
                "estimated_amount": "850.00",
                "expected_updated_at": self.ledger.updated_at.isoformat(),
                "participant_plans": [
                    {"member": str(self.owner.id), "spending_limit": "350.00", "planned_share": "450.25"},
                    {"member": str(self.adult.id), "planned_share": "450.25"},
                ],
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.ledger.refresh_from_db()
        self.assertEqual(self.ledger.budget_amount, Decimal("900.50"))
        self.assertEqual(self.ledger.estimated_amount, Decimal("850.00"))
        root_rows = ExpenseBudgetParticipantPlan.objects.filter(ledger=self.ledger, budget__isnull=True)
        self.assertEqual(root_rows.count(), 2)
        self.assertEqual(root_rows.get(member=self.owner).spending_limit, Decimal("350.00"))
        self.assertEqual(Expense.objects.count(), 0)
        self.assertEqual(ExpenseShare.objects.count(), 0)
        self.assertEqual(Settlement.objects.count(), 0)

        projection = self.client.get(f"/api/expense-ledgers/{self.ledger.id}/participant-plans/")
        self.assertEqual(projection.status_code, 200, projection.data)
        self.assertEqual(projection.data["scope_type"], "ledger")
        self.assertEqual(projection.data["scope_id"], str(self.ledger.id))
        self.assertTrue(projection.data["can_manage"])

    def test_foreign_member_rolls_back_overall_budget_change(self):
        original_amount = self.ledger.budget_amount
        response = self.client.patch(
            f"/api/expense-ledgers/{self.ledger.id}/participant-plans/",
            {
                "family": str(self.family.id),
                "budget_amount": "777.00",
                "expected_updated_at": self.ledger.updated_at.isoformat(),
                "participant_plans": [
                    {"member": str(self.foreign_member.id), "spending_limit": "20.00"},
                ],
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400, response.data)
        self.ledger.refresh_from_db()
        self.assertEqual(self.ledger.budget_amount, original_amount)
        self.assertFalse(ExpenseBudgetParticipantPlan.objects.filter(ledger=self.ledger, budget__isnull=True).exists())

    def test_foreign_member_rejects_whole_budget_create(self):
        request_id = str(uuid4())
        response = self.client.post(
            "/api/expense-budgets/",
            {
                "family": str(self.family.id),
                "ledger": str(self.ledger.id),
                "name": "Nicht speichern",
                "amount": "100.00",
                "client_request_id": request_id,
                "participant_plans": [
                    {"member": str(self.foreign_member.id), "spending_limit": "20.00"},
                ],
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400, response.data)
        self.assertFalse(ExpenseBudget.objects.filter(client_request_id=request_id).exists())
        self.assertEqual(ExpenseBudgetParticipantPlan.objects.count(), 0)

    def test_adult_can_replace_plan_and_empty_list_clears_it(self):
        created = self.create_budget(
            participant_plans=[{"member": str(self.owner.id), "spending_limit": "100.00"}]
        )
        budget = ExpenseBudget.objects.get(id=created.data["id"])
        self.client.force_authenticate(self.adult_user)
        response = self.client.patch(
            f"/api/expense-budgets/{budget.id}/",
            {
                "family": str(self.family.id),
                "expected_updated_at": created.data["updated_at"],
                "participant_plans": [
                    {"member": str(self.adult.id), "spending_limit": "80.00", "planned_share": "250.00"}
                ],
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(budget.participant_plans.count(), 1)
        self.assertEqual(budget.participant_plans.get().member_id, self.adult.id)

        cleared = self.client.patch(
            f"/api/expense-budgets/{budget.id}/",
            {
                "family": str(self.family.id),
                "expected_updated_at": response.data["updated_at"],
                "participant_plans": [],
            },
            format="json",
        )
        self.assertEqual(cleared.status_code, 200, cleared.data)
        self.assertEqual(budget.participant_plans.count(), 0)

    def test_teen_cannot_write_participant_plans_and_budget_change_rolls_back(self):
        created = self.create_budget()
        budget = ExpenseBudget.objects.get(id=created.data["id"])
        self.client.force_authenticate(self.teen_user)
        response = self.client.patch(
            f"/api/expense-budgets/{budget.id}/",
            {
                "family": str(self.family.id),
                "amount": "999.00",
                "expected_updated_at": created.data["updated_at"],
                "participant_plans": [
                    {"member": str(self.teen.id), "spending_limit": "40.00"}
                ],
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400, response.data)
        budget.refresh_from_db()
        self.assertEqual(budget.amount, Decimal("600.00"))
        self.assertEqual(budget.participant_plans.count(), 0)

    def test_teen_cannot_write_overall_participant_plans(self):
        self.client.force_authenticate(self.teen_user)
        response = self.client.patch(
            f"/api/expense-ledgers/{self.ledger.id}/participant-plans/",
            {
                "family": str(self.family.id),
                "budget_amount": "999.00",
                "expected_updated_at": self.ledger.updated_at.isoformat(),
                "participant_plans": [
                    {"member": str(self.teen.id), "spending_limit": "40.00"}
                ],
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400, response.data)
        self.ledger.refresh_from_db()
        self.assertIsNone(self.ledger.budget_amount)
        self.assertFalse(ExpenseBudgetParticipantPlan.objects.filter(ledger=self.ledger, budget__isnull=True).exists())

    def test_read_projection_redacts_other_person_limits_for_teen_but_keeps_planned_shares(self):
        created = self.create_budget(
            participant_plans=[
                {"member": str(self.owner.id), "spending_limit": "120.00", "planned_share": "250.00"},
                {"member": str(self.teen.id), "spending_limit": "50.00", "planned_share": "100.00"},
            ]
        )
        budget_id = created.data["id"]

        manager = self.client.get(f"/api/expense-budgets/{budget_id}/participant-plans/")
        self.assertEqual(manager.status_code, 200, manager.data)
        self.assertTrue(manager.data["can_manage"])
        self.assertEqual(manager.data["scope_type"], "budget")
        manager_rows = {row["member"]: row for row in manager.data["plans"]}
        self.assertEqual(manager_rows[str(self.owner.id)]["spending_limit"], "120.00")
        self.assertEqual(manager_rows[str(self.teen.id)]["spending_limit"], "50.00")

        self.client.force_authenticate(self.teen_user)
        teen_response = self.client.get(f"/api/expense-budgets/{budget_id}/participant-plans/")
        self.assertEqual(teen_response.status_code, 200, teen_response.data)
        self.assertFalse(teen_response.data["can_manage"])
        teen_rows = {row["member"]: row for row in teen_response.data["plans"]}
        self.assertIsNone(teen_rows[str(self.owner.id)]["spending_limit"])
        self.assertFalse(teen_rows[str(self.owner.id)]["spending_limit_visible"])
        self.assertEqual(teen_rows[str(self.owner.id)]["planned_share"], "250.00")
        self.assertEqual(teen_rows[str(self.teen.id)]["spending_limit"], "50.00")
        self.assertTrue(teen_rows[str(self.teen.id)]["spending_limit_visible"])
        self.assertEqual(teen_rows[str(self.teen.id)]["planned_share"], "100.00")

    def test_retry_signature_is_idempotent_but_changed_participant_plan_conflicts(self):
        request_id = str(uuid4())
        payload = {
            "family": str(self.family.id),
            "ledger": str(self.ledger.id),
            "name": "Retry",
            "amount": "200.00",
            "client_request_id": request_id,
            "participant_plans": [
                {"member": str(self.owner.id), "spending_limit": "75.00", "planned_share": "100.00"}
            ],
        }
        first = self.client.post("/api/expense-budgets/", payload, format="json")
        self.assertEqual(first.status_code, 201, first.data)
        second = self.client.post("/api/expense-budgets/", payload, format="json")
        self.assertEqual(second.status_code, 201, second.data)
        self.assertEqual(first.data["id"], second.data["id"])
        self.assertEqual(ExpenseBudget.objects.filter(client_request_id=request_id).count(), 1)
        self.assertEqual(ExpenseBudgetParticipantPlan.objects.count(), 1)

        changed = {
            **payload,
            "participant_plans": [
                {"member": str(self.owner.id), "spending_limit": "76.00", "planned_share": "100.00"}
            ],
        }
        conflict = self.client.post("/api/expense-budgets/", changed, format="json")
        self.assertEqual(conflict.status_code, 409, conflict.data)
        self.assertEqual(ExpenseBudgetParticipantPlan.objects.get().spending_limit, Decimal("75.00"))

    def test_budget_summary_does_not_expose_personal_participant_planning(self):
        self.client.patch(
            f"/api/expense-ledgers/{self.ledger.id}/participant-plans/",
            {
                "family": str(self.family.id),
                "budget_amount": "900.00",
                "expected_updated_at": self.ledger.updated_at.isoformat(),
                "participant_plans": [
                    {"member": str(self.owner.id), "spending_limit": "400.00", "planned_share": "450.00"}
                ],
            },
            format="json",
        )
        self.create_budget(
            participant_plans=[
                {"member": str(self.owner.id), "spending_limit": "120.00", "planned_share": "300.00"}
            ]
        )
        summary = self.client.get(f"/api/expense-ledgers/{self.ledger.id}/budget-summary/")
        self.assertEqual(summary.status_code, 200, summary.data)
        encoded = str(summary.data)
        self.assertNotIn("participant_plans", encoded)
        self.assertNotIn("spending_limit", encoded)
        self.assertNotIn("planned_share", encoded)
