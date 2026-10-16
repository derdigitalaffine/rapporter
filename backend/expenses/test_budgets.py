from decimal import Decimal
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient

from family.models import Family, Membership
from .models import (
    Expense,
    ExpenseBudget,
    ExpenseBudgetAllocation,
    ExpenseLedger,
    ExpenseShare,
    get_default_expense_ledger,
)

User = get_user_model()


class ExpenseBudgetCoreTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="budget-owner", password="test")
        self.sam_user = User.objects.create_user(username="budget-sam", password="test")
        self.foreign_user = User.objects.create_user(username="budget-foreign", password="test")
        self.family = Family.objects.create(name="Budget Familie", slug="budget-familie")
        self.foreign_family = Family.objects.create(name="Fremde Budget Familie", slug="fremde-budget-familie")
        self.owner = Membership.objects.create(
            family=self.family,
            user=self.user,
            role=Membership.Role.OWNER,
            display_name="Alex",
        )
        self.sam = Membership.objects.create(
            family=self.family,
            user=self.sam_user,
            role=Membership.Role.ADULT,
            display_name="Sam",
        )
        Membership.objects.create(
            family=self.foreign_family,
            user=self.foreign_user,
            role=Membership.Role.OWNER,
            display_name="Fremd",
        )
        self.ledger = get_default_expense_ledger(self.family)
        self.foreign_ledger = get_default_expense_ledger(self.foreign_family)
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def _expense(self, amount="10.00", *, ledger=None, currency="EUR"):
        ledger = ledger or self.ledger
        expense = Expense.objects.create(
            family=self.family,
            ledger=ledger,
            title="Budget Test",
            total_amount=Decimal(amount),
            currency=currency,
            paid_by=self.owner,
            created_by=self.user,
        )
        half = (Decimal(amount) / Decimal("2")).quantize(Decimal("0.01"))
        ExpenseShare.objects.create(expense=expense, member=self.owner, amount=half)
        ExpenseShare.objects.create(
            expense=expense,
            member=self.sam,
            amount=Decimal(amount) - half,
        )
        return expense

    def _budget(self, name="Lebensmittel", amount="100.00", *, ledger=None, archived=False):
        ledger = ledger or self.ledger
        return ExpenseBudget.objects.create(
            family=self.family,
            ledger=ledger,
            name=name,
            amount=Decimal(amount),
            archived=archived,
        )

    def _allocation_url(self, expense):
        return f"/api/expenses/{expense.id}/budget-allocations/"

    def test_budget_create_is_ledger_scoped_and_foreign_ledger_is_rejected(self):
        response = self.client.post(
            "/api/expense-budgets/",
            {
                "family": str(self.family.id),
                "ledger": str(self.ledger.id),
                "name": "Freizeit",
                "amount": "80.00",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        budget = ExpenseBudget.objects.get(id=response.data["id"])
        self.assertEqual(budget.family_id, self.family.id)
        self.assertEqual(budget.ledger_id, self.ledger.id)

        foreign = self.client.post(
            "/api/expense-budgets/",
            {
                "family": str(self.family.id),
                "ledger": str(self.foreign_ledger.id),
                "name": "Nicht erlaubt",
                "amount": "10.00",
            },
            format="json",
        )
        self.assertEqual(foreign.status_code, 400, foreign.data)
        self.assertIn("ledger", foreign.data)

    def test_ledger_base_currency_is_locked_after_expense_activity(self):
        self._expense("10.00")
        response = self.client.patch(
            f"/api/expense-ledgers/{self.ledger.id}/",
            {"base_currency": "USD"},
            format="json",
        )
        self.assertEqual(response.status_code, 400, response.data)
        self.assertIn("base_currency", response.data)
        self.ledger.refresh_from_db()
        self.assertEqual(self.ledger.base_currency, "EUR")

    def test_single_budget_allocation_requires_exact_expense_total(self):
        expense = self._expense("10.00")
        budget = self._budget()
        response = self.client.put(
            self._allocation_url(expense),
            {
                "allocations": [
                    {"budget": str(budget.id), "amount_in_budget_currency": "10.00"},
                ]
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(len(response.data["allocations"]), 1)
        allocation = ExpenseBudgetAllocation.objects.get(expense=expense)
        self.assertEqual(allocation.amount_in_budget_currency, Decimal("10.00"))

    def test_multi_budget_allocation_is_cent_exact(self):
        expense = self._expense("10.01")
        food = self._budget("Essen")
        leisure = self._budget("Freizeit")
        response = self.client.put(
            self._allocation_url(expense),
            {
                "allocations": [
                    {"budget": str(food.id), "amount_in_budget_currency": "5.00"},
                    {"budget": str(leisure.id), "amount_in_budget_currency": "5.01"},
                ]
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        total = sum(
            ExpenseBudgetAllocation.objects.filter(expense=expense).values_list(
                "amount_in_budget_currency", flat=True
            ),
            Decimal("0.00"),
        )
        self.assertEqual(total, Decimal("10.01"))

    def test_invalid_replacement_is_atomic_and_preserves_previous_allocation(self):
        expense = self._expense("10.00")
        budget = self._budget()
        valid = self.client.put(
            self._allocation_url(expense),
            {"allocations": [{"budget": str(budget.id), "amount_in_budget_currency": "10.00"}]},
            format="json",
        )
        self.assertEqual(valid.status_code, 200, valid.data)

        invalid = self.client.put(
            self._allocation_url(expense),
            {"allocations": [{"budget": str(budget.id), "amount_in_budget_currency": "9.99"}]},
            format="json",
        )
        self.assertEqual(invalid.status_code, 400, invalid.data)
        allocation = ExpenseBudgetAllocation.objects.get(expense=expense)
        self.assertEqual(allocation.budget_id, budget.id)
        self.assertEqual(allocation.amount_in_budget_currency, Decimal("10.00"))

    def test_cross_ledger_and_archived_budget_ids_fail_closed(self):
        expense = self._expense("10.00")
        other_ledger = ExpenseLedger.objects.create(
            family=self.family,
            name="Reise",
            base_currency="EUR",
        )
        other_budget = self._budget("Reisebudget", ledger=other_ledger)
        archived = self._budget("Alt", archived=True)

        cross_ledger = self.client.put(
            self._allocation_url(expense),
            {"allocations": [{"budget": str(other_budget.id), "amount_in_budget_currency": "10.00"}]},
            format="json",
        )
        self.assertEqual(cross_ledger.status_code, 400, cross_ledger.data)
        self.assertEqual(ExpenseBudgetAllocation.objects.filter(expense=expense).count(), 0)

        archived_response = self.client.put(
            self._allocation_url(expense),
            {"allocations": [{"budget": str(archived.id), "amount_in_budget_currency": "10.00"}]},
            format="json",
        )
        self.assertEqual(archived_response.status_code, 400, archived_response.data)
        self.assertEqual(ExpenseBudgetAllocation.objects.filter(expense=expense).count(), 0)

    def test_foreign_family_budget_id_is_rejected_without_writing(self):
        expense = self._expense("10.00")
        foreign_budget = ExpenseBudget.objects.create(
            family=self.foreign_family,
            ledger=self.foreign_ledger,
            name="Fremd",
            amount=Decimal("10.00"),
        )
        response = self.client.put(
            self._allocation_url(expense),
            {"allocations": [{"budget": str(foreign_budget.id), "amount_in_budget_currency": "10.00"}]},
            format="json",
        )
        self.assertEqual(response.status_code, 400, response.data)
        self.assertEqual(ExpenseBudgetAllocation.objects.filter(expense=expense).count(), 0)

    def test_soft_overall_budget_reports_overrun_but_never_blocks_expense(self):
        self.ledger.budget_amount = Decimal("5.00")
        self.ledger.save(update_fields=["budget_amount", "updated_at"])
        response = self.client.post(
            "/api/expenses/",
            {
                "family": str(self.family.id),
                "ledger": str(self.ledger.id),
                "title": "Über Budget",
                "total_amount": "12.00",
                "currency": "EUR",
                "participants": [str(self.owner.id), str(self.sam.id)],
                "split_type": "equal",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)

        summary = self.client.get(f"/api/expense-ledgers/{self.ledger.id}/budget-summary/")
        self.assertEqual(summary.status_code, 200, summary.data)
        self.assertEqual(summary.data["budget_amount"], "5.00")
        self.assertEqual(summary.data["spent_amount"], "12.00")
        self.assertEqual(summary.data["remaining_amount"], "-7.00")
        self.assertTrue(summary.data["over_budget"])

    def test_foreign_currency_is_not_silently_converted(self):
        expense = self._expense("10.00", currency="USD")
        budget = self._budget()
        allocation = self.client.put(
            self._allocation_url(expense),
            {"allocations": [{"budget": str(budget.id), "amount_in_budget_currency": "10.00"}]},
            format="json",
        )
        self.assertEqual(allocation.status_code, 400, allocation.data)
        self.assertIn("Fremdwährungsumrechnung", str(allocation.data))

        summary = self.client.get(f"/api/expense-ledgers/{self.ledger.id}/budget-summary/")
        self.assertEqual(summary.status_code, 200, summary.data)
        self.assertEqual(summary.data["spent_amount"], "0.00")
        self.assertEqual(summary.data["unconverted_expense_count"], 1)

    def test_amount_change_clears_stale_budget_allocations(self):
        expense = self._expense("10.00")
        budget = self._budget()
        response = self.client.put(
            self._allocation_url(expense),
            {"allocations": [{"budget": str(budget.id), "amount_in_budget_currency": "10.00"}]},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(ExpenseBudgetAllocation.objects.filter(expense=expense).count(), 1)

        expense.total_amount = Decimal("12.00")
        expense.save(update_fields=["total_amount", "updated_at"])
        self.assertEqual(ExpenseBudgetAllocation.objects.filter(expense=expense).count(), 0)

    def test_empty_replacement_clears_budget_allocation(self):
        expense = self._expense("10.00")
        budget = self._budget()
        self.client.put(
            self._allocation_url(expense),
            {"allocations": [{"budget": str(budget.id), "amount_in_budget_currency": "10.00"}]},
            format="json",
        )
        response = self.client.put(
            self._allocation_url(expense),
            {"allocations": []},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["allocations"], [])
        self.assertEqual(ExpenseBudgetAllocation.objects.filter(expense=expense).count(), 0)

    def test_estimates_and_plans_do_not_post_expenses_or_change_balances(self):
        expense = self._expense("10.00")
        shares = list(expense.shares.values_list("member_id", "amount"))
        before = self.client.get(f"/api/expenses/balance/?family={self.family.id}").data
        response = self.client.patch(
            f"/api/expense-ledgers/{self.ledger.id}/",
            {"budget_amount": "1200,50", "estimated_amount": "1350,75", "expected_updated_at": self.ledger.updated_at.isoformat()},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        budget = self.client.post(
            "/api/expense-budgets/",
            {"family": str(self.family.id), "ledger": str(self.ledger.id), "name": "Unterkunft", "amount": "800.25", "estimated_amount": "900.50"},
            format="json",
        )
        self.assertEqual(budget.status_code, 201, budget.data)
        summary = self.client.get(f"/api/expense-ledgers/{self.ledger.id}/budget-summary/").data
        self.assertEqual(summary["estimated_amount"], "1350.75")
        self.assertEqual(summary["budget_amount"], "1200.50")
        self.assertEqual(summary["spent_amount"], "10.00")
        self.assertEqual(summary["remaining_amount"], "1190.50")
        self.assertEqual(summary["budgets"][0]["estimated_amount"], "900.50")
        self.assertEqual(summary["budgets"][0]["spent_amount"], Decimal("0.00"))
        self.assertEqual(Expense.objects.filter(family=self.family).count(), 1)
        self.assertEqual(shares, list(expense.shares.values_list("member_id", "amount")))
        self.assertEqual(before, self.client.get(f"/api/expenses/balance/?family={self.family.id}").data)

    def test_estimate_is_nullable_zero_is_explicit_and_invalid_money_is_rejected(self):
        budget = self._budget()
        for url in [f"/api/expense-ledgers/{self.ledger.id}/", f"/api/expense-budgets/{budget.id}/"]:
            for value in ["-0.01", "1.001", "10000000000", "NaN", "Infinity"]:
                response = self.client.patch(url, {"estimated_amount": value}, format="json")
                self.assertEqual(response.status_code, 400, response.data)
            for value, expected in [("0.00", "0.00"), (None, None)]:
                response = self.client.patch(url, {"estimated_amount": value}, format="json")
                self.assertEqual(response.status_code, 200, response.data)
                self.assertEqual(response.data["estimated_amount"], expected)

    def test_stale_revision_cannot_overwrite_plan_or_archive_category(self):
        budget = self._budget()
        for obj, amount_field in [(self.ledger, "budget_amount"), (budget, "amount")]:
            route = "expense-ledgers" if isinstance(obj, ExpenseLedger) else "expense-budgets"
            url = f"/api/{route}/{obj.id}/"
            revision = obj.updated_at.isoformat()
            first = self.client.patch(url, {amount_field: "200.50", "expected_updated_at": revision}, format="json")
            self.assertEqual(first.status_code, 200, first.data)
            stale_payload = {amount_field: "700.00", "expected_updated_at": revision}
            if isinstance(obj, ExpenseBudget):
                stale_payload["archived"] = True
            stale = self.client.patch(url, stale_payload, format="json")
            self.assertEqual(stale.status_code, 409, stale.data)
            obj.refresh_from_db()
            self.assertEqual(getattr(obj, amount_field), Decimal("200.50"))
            self.assertFalse(obj.archived)
            current = self.client.patch(url, {amount_field: "250.75", "expected_updated_at": first.data["updated_at"]}, format="json")
            self.assertEqual(current.status_code, 200, current.data)

    def test_budget_create_retry_returns_same_canonical_category(self):
        payload = {"family": str(self.family.id), "ledger": str(self.ledger.id), "name": "Transport", "amount": "400.00", "client_request_id": str(uuid4())}
        first = self.client.post("/api/expense-budgets/", payload, format="json")
        retry = self.client.post("/api/expense-budgets/", payload, format="json")
        self.assertEqual(first.status_code, 201, first.data)
        self.assertEqual(retry.status_code, 201, retry.data)
        self.assertEqual(first.data["id"], retry.data["id"])
        self.assertEqual(ExpenseBudget.objects.filter(ledger=self.ledger).count(), 1)
        self.assertNotIn("client_request_id", first.data)
        self.assertNotIn("expected_updated_at", first.data)

    def test_budget_creation_key_is_ledger_scoped_and_immutable_on_update(self):
        other = ExpenseLedger.objects.create(family=self.family, name="Projekt", base_currency="EUR")
        request_id = str(uuid4())
        created = []
        for ledger in [self.ledger, other]:
            response = self.client.post("/api/expense-budgets/", {"family": str(self.family.id), "ledger": str(ledger.id), "name": "Transport", "amount": "1.00", "client_request_id": request_id}, format="json")
            self.assertEqual(response.status_code, 201, response.data)
            created.append(response.data["id"])
        self.assertNotEqual(*created)
        response = self.client.patch(f"/api/expense-budgets/{created[0]}/", {"client_request_id": str(uuid4()), "name": "Anreise"}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(str(ExpenseBudget.objects.get(pk=created[0]).client_request_id), request_id)

    def test_retry_key_with_changed_input_does_not_silently_discard_changes(self):
        payload = {"family": str(self.family.id), "ledger": str(self.ledger.id), "name": "Transport", "amount": "100.00", "client_request_id": str(uuid4())}
        first = self.client.post("/api/expense-budgets/", payload, format="json")
        self.assertEqual(first.status_code, 201, first.data)
        changed = self.client.post("/api/expense-budgets/", {**payload, "amount": "200.00"}, format="json")
        self.assertEqual(changed.status_code, 409, changed.data)
        self.assertEqual(ExpenseBudget.objects.get(pk=first.data["id"]).amount, Decimal("100.00"))
        self.assertEqual(ExpenseBudget.objects.filter(ledger=self.ledger).count(), 1)

    def test_foreign_or_revoked_membership_cannot_read_or_change_planning(self):
        budget = ExpenseBudget.objects.create(family=self.foreign_family, ledger=self.foreign_ledger, name="Privater Bereich", amount=Decimal("100.00"))
        for url in [f"/api/expense-ledgers/{self.foreign_ledger.id}/", f"/api/expense-budgets/{budget.id}/"]:
            self.assertEqual(self.client.get(url).status_code, 404)
            self.assertEqual(self.client.patch(url, {"estimated_amount": "42.00"}, format="json").status_code, 404)
        self.assertEqual(self.client.get(f"/api/expense-ledgers/{self.foreign_ledger.id}/budget-summary/").status_code, 404)
        own = self._budget()
        self.owner.delete()
        response = self.client.patch(f"/api/expense-budgets/{own.id}/", {"estimated_amount": "42.00"}, format="json")
        self.assertEqual(response.status_code, 403)
        own.refresh_from_db()
        self.assertIsNone(own.estimated_amount)

    def test_category_archive_keeps_expense_history_and_allocations(self):
        budget = self._budget()
        expense = self._expense()
        ExpenseBudgetAllocation.objects.create(expense=expense, budget=budget, amount_in_budget_currency=Decimal("10.00"))
        response = self.client.patch(f"/api/expense-budgets/{budget.id}/", {"archived": True, "expected_updated_at": budget.updated_at.isoformat()}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        summary = self.client.get(f"/api/expense-ledgers/{self.ledger.id}/budget-summary/").data
        self.assertEqual(summary["budgets"], [])
        self.assertEqual(summary["spent_amount"], "10.00")
        self.assertTrue(ExpenseBudgetAllocation.objects.filter(expense=expense, budget=budget).exists())

    def test_summary_and_list_query_count_does_not_grow_per_category(self):
        self._budget()
        urls = [f"/api/expense-ledgers/{self.ledger.id}/budget-summary/", f"/api/expense-budgets/?family={self.family.id}&ledger={self.ledger.id}"]
        counts = []
        for url in urls:
            with CaptureQueriesContext(connection) as queries:
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200, response.data)
            counts.append(len(queries))
        for index in range(5):
            self._budget(name=f"Kostenbereich {index}")
        for url, expected_count in zip(urls, counts):
            with CaptureQueriesContext(connection) as queries:
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200, response.data)
            self.assertEqual(len(queries), expected_count)

    def test_hierarchy_sums_descendants_and_miscellaneous_without_double_counting(self):
        from .commitment_models import BudgetCommitment
        self.ledger.budget_amount = Decimal('1000.00')
        self.ledger.save()
        parent = self._budget('Mobilität', '300.00')
        child = self._budget('Bahn', '100.00')
        child.parent = parent
        child.save()
        grandchild = self._budget('Pendeln', '60.00')
        grandchild.parent = child
        grandchild.save()
        for budget, value in [(parent, '10.01'), (child, '20.02'), (grandchild, '30.03')]:
            expense = self._expense(value)
            ExpenseBudgetAllocation.objects.create(expense=expense, budget=budget, amount_in_budget_currency=value)
        self._expense('5.04')
        for budget, value in [(None, '3.01'), (parent, '4.02'), (grandchild, '5.03')]:
            BudgetCommitment.objects.create(family=self.family, ledger=self.ledger, budget=budget, amount=value, currency='EUR', source_type='shopping_item', source_id=uuid4())
        response = self.client.get(f'/api/expense-ledgers/{self.ledger.id}/budget-summary/')
        self.assertEqual(response.status_code, 200, response.data)
        rows = {row['name']: row for row in response.data['budgets']}
        h = rows['Mobilität']['hierarchy']
        self.assertEqual(h['spent_amount'], '60.06')
        self.assertEqual(h['reserved_amount'], '9.05')
        self.assertEqual(h['available_amount'], '230.89')
        self.assertEqual(h['miscellaneous_amount'], '200.00')
        self.assertEqual(h['miscellaneous_spent_amount'], '10.01')
        self.assertEqual(h['miscellaneous_reserved_amount'], '4.02')
        self.assertEqual(rows['Bahn']['hierarchy']['miscellaneous_amount'], '40.00')
        self.assertEqual(rows['Pendeln']['hierarchy']['miscellaneous_amount'], '60.00')
        root = response.data['hierarchy']
        self.assertEqual(root['children_amount'], '300.00')
        self.assertEqual(root['miscellaneous_amount'], '700.00')
        self.assertEqual(root['miscellaneous_spent_amount'], '5.04')
        self.assertEqual(root['miscellaneous_reserved_amount'], '3.01')
        self.assertEqual(response.data['spent_amount'], '65.10')
        self.assertNotIn('participant_plans', str(response.data))

    def test_hierarchy_overplanning_and_archived_intermediates_remain_visible(self):
        parent = self._budget('Parent', '10.00')
        archived = self._budget('Archived', '5.00', archived=True)
        archived.parent = parent
        archived.save()
        child = self._budget('Child', '20.01')
        child.parent = archived
        child.save()
        expense = self._expense('2.01')
        ExpenseBudgetAllocation.objects.create(expense=expense, budget=archived, amount_in_budget_currency='2.01')
        data = self.client.get(f'/api/expense-ledgers/{self.ledger.id}/budget-summary/').data
        rows = {row['name']: row for row in data['budgets']}
        self.assertEqual(rows['Child']['hierarchy']['parent'], str(parent.id))
        self.assertEqual(rows['Parent']['hierarchy']['miscellaneous_amount'], '-10.01')
        self.assertTrue(rows['Parent']['hierarchy']['overplanned'])
        self.assertEqual(rows['Parent']['hierarchy']['miscellaneous_spent_amount'], '2.01')
        self.assertEqual(data['hierarchy']['miscellaneous_amount'], None)

    def test_miscellaneous_plan_rejects_stale_child_total_on_parent_and_root(self):
        parent = self._budget('Parent', '100.00')
        child = self._budget('Child', '20.00')
        child.parent = parent
        child.save()
        for url, amount_field, expected in [
            (f'/api/expense-budgets/{parent.id}/', 'amount', '19.99'),
            (f'/api/expense-ledgers/{self.ledger.id}/', 'budget_amount', '99.99'),
        ]:
            response = self.client.patch(url, {amount_field: '150.00', 'expected_children_amount': expected}, format='json')
            self.assertEqual(response.status_code, 409, response.data)
        response = self.client.patch(f'/api/expense-budgets/{parent.id}/', {'amount': '150.00', 'expected_children_amount': '20.00'}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertNotIn('expected_children_amount', response.data)

    def test_parent_move_rejects_cycle_and_foreign_parent_without_changes(self):
        parent = self._budget('Parent')
        child = self._budget('Child')
        child.parent = parent
        child.save()
        foreign = ExpenseBudget.objects.create(family=self.foreign_family, ledger=self.foreign_ledger, name='Foreign', amount='1.00')
        for target in [child, parent, foreign]:
            response = self.client.patch(f'/api/expense-budgets/{parent.id}/', {'parent': str(target.id)}, format='json')
            self.assertEqual(response.status_code, 400, response.data)
        parent.refresh_from_db()
        self.assertIsNone(parent.parent_id)
