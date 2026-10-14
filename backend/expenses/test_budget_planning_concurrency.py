from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Barrier
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.db import close_old_connections
from django.test import TransactionTestCase
from rest_framework.test import APIClient

from entitlements.models import CapabilityDefinition
from family.models import Family, Membership
from .models import ExpenseBudget, get_default_expense_ledger


class BudgetPlanningConcurrencyTests(TransactionTestCase):
    def setUp(self):
        # TransactionTestCase flushes migration-seeded catalog rows between tests.
        CapabilityDefinition.objects.update_or_create(key="expenses", defaults={"domain": "expenses", "premium": True})
        self.user = get_user_model().objects.create_user(username="budget-concurrency")
        self.family = Family.objects.create(name="Budget concurrency", slug="budget-concurrency")
        Membership.objects.create(family=self.family, user=self.user, role=Membership.Role.OWNER)
        self.ledger = get_default_expense_ledger(self.family)

    def _race(self, method, url, payloads):
        barrier = Barrier(2)

        def write(payload):
            close_old_connections()
            try:
                client = APIClient()
                client.force_authenticate(self.user)
                barrier.wait(timeout=10)
                response = getattr(client, method)(url, payload, format="json")
                return response.status_code, response.data
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as pool:
            return list(pool.map(write, payloads))

    def test_two_editors_with_same_revision_cannot_both_commit(self):
        payloads = [{"expected_updated_at": self.ledger.updated_at.isoformat(), "budget_amount": amount} for amount in ["100.25", "200.50"]]
        results = self._race("patch", f"/api/expense-ledgers/{self.ledger.id}/", payloads)
        self.assertEqual(sorted(code for code, _ in results), [200, 409], results)
        committed = next(data for code, data in results if code == 200)
        self.ledger.refresh_from_db()
        self.assertEqual(self.ledger.budget_amount, Decimal(committed["budget_amount"]))

    def test_simultaneous_category_retry_creates_one_budget(self):
        payload = {"family": str(self.family.id), "ledger": str(self.ledger.id), "name": "Unterkunft", "amount": "100.25", "client_request_id": str(uuid4())}
        results = self._race("post", "/api/expense-budgets/", [payload, payload])
        self.assertEqual([code for code, _ in results], [201, 201], results)
        self.assertEqual(results[0][1]["id"], results[1][1]["id"])
        self.assertEqual(ExpenseBudget.objects.filter(ledger=self.ledger).count(), 1)
