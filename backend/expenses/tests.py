import io
from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from PIL import Image
from rest_framework.test import APIClient

from family.models import Family, Membership
from .models import Expense, ExpenseShare, ReceiptExtraction, Settlement
from .money import balance_summary, build_split, simplify_balances
from .ocr import parse_receipt_text

User = get_user_model()


class MoneyTests(TestCase):
    def test_equal_split_is_cent_exact_and_deterministic(self):
        ids = ["00000000-0000-0000-0000-000000000003", "00000000-0000-0000-0000-000000000001", "00000000-0000-0000-0000-000000000002"]
        first = build_split("10.00", ids, "equal")
        second = build_split("10.00", reversed(ids), "equal")
        self.assertEqual(first, second)
        self.assertEqual(sum(first.values()), Decimal("10.00"))
        self.assertEqual(sorted(first.values()), [Decimal("3.33"), Decimal("3.33"), Decimal("3.34")])

    def test_percentage_split_is_cent_exact(self):
        ids = ["a", "b", "c"]
        result = build_split("19.99", ids, "percentage", {"a": "33.33", "b": "33.33", "c": "33.34"})
        self.assertEqual(sum(result.values()), Decimal("19.99"))

    def test_exact_split_rejects_mismatch(self):
        with self.assertRaises(ValueError):
            build_split("10.00", ["a", "b"], "exact", {"a": "4.00", "b": "5.00"})


class ReceiptParserTests(TestCase):
    def test_receipt_fixture_extracts_core_fields_with_confidence(self):
        parsed = parse_receipt_text("REWE MARKT\nMannheim\n08.10.2026\nMilch 2,19\nBrot 3,15\nSUMME EUR 12,34\nGEGEBEN 20,00")
        self.assertEqual(parsed["merchant"], "REWE MARKT")
        self.assertEqual(parsed["date"], date(2026, 10, 8))
        self.assertEqual(parsed["total"], Decimal("12.34"))
        self.assertEqual(parsed["currency"], "EUR")
        self.assertGreater(parsed["field_confidences"]["total"], 0.8)


class ExpenseApiTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="alex", password="test")
        self.other = User.objects.create_user(username="sam", password="test")
        self.outsider = User.objects.create_user(username="outsider", password="test")
        self.family = Family.objects.create(name="Familie", slug="familie")
        self.alex = Membership.objects.create(family=self.family, user=self.user, role=Membership.Role.OWNER, display_name="Alex")
        self.sam = Membership.objects.create(family=self.family, user=self.other, role=Membership.Role.ADULT, display_name="Sam")
        self.other_family = Family.objects.create(name="Andere", slug="andere")
        self.other_membership = Membership.objects.create(family=self.other_family, user=self.outsider, display_name="Outsider")
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_create_expense_and_balance(self):
        response = self.client.post("/api/expenses/", {
            "family": str(self.family.id),
            "title": "Einkauf",
            "total_amount": "10.00",
            "currency": "EUR",
            "paid_by": str(self.alex.id),
            "participants": [str(self.alex.id), str(self.sam.id)],
            "split_type": "equal",
        }, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        expense = Expense.objects.get(id=response.data["id"])
        self.assertEqual(sum(expense.shares.values_list("amount", flat=True)), Decimal("10.00"))
        balance = self.client.get(f"/api/expenses/balance/?family={self.family.id}&currency=EUR")
        self.assertEqual(balance.status_code, 200)
        rows = {row["name"]: Decimal(row["balance"]) for row in balance.data["members"]}
        self.assertEqual(rows["Alex"], Decimal("5.00"))
        self.assertEqual(rows["Sam"], Decimal("-5.00"))

    def test_settlement_changes_balance_without_creating_expense(self):
        expense = Expense.objects.create(family=self.family, title="Taxi", total_amount="20.00", currency="EUR", paid_by=self.alex, created_by=self.user)
        ExpenseShare.objects.create(expense=expense, member=self.alex, amount="10.00")
        ExpenseShare.objects.create(expense=expense, member=self.sam, amount="10.00")
        response = self.client.post("/api/expense-settlements/", {
            "family": str(self.family.id), "from_member": str(self.sam.id), "to_member": str(self.alex.id), "amount": "10.00", "currency": "EUR"
        }, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(Expense.objects.count(), 1)
        summary = balance_summary(self.family, "EUR")
        self.assertTrue(all(row["balance"] == Decimal("0.00") for row in summary.values()))
        self.assertEqual(simplify_balances(summary), [])

    def test_cross_family_expense_is_not_visible(self):
        foreign = Expense.objects.create(family=self.other_family, title="Privat", total_amount="5.00", paid_by=self.other_membership, created_by=self.outsider)
        response = self.client.get(f"/api/expenses/{foreign.id}/")
        self.assertEqual(response.status_code, 404)

    @patch("expenses.views.enqueue_receipt_extraction")
    def test_receipt_upload_creates_private_queued_draft(self, enqueue):
        image = Image.new("RGB", (900, 1200), "white")
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        upload = SimpleUploadedFile("receipt.png", buffer.getvalue(), content_type="image/png")
        response = self.client.post("/api/expenses/receipt/", {"family": str(self.family.id), "receipt": upload}, format="multipart")
        self.assertEqual(response.status_code, 202, response.data)
        expense = Expense.objects.get(id=response.data["id"])
        self.assertEqual(expense.status, Expense.Status.DRAFT)
        self.assertEqual(expense.receipt_status, Expense.ReceiptStatus.QUEUED)
        self.assertEqual(expense.receipt_mime, "image/jpeg")
        self.assertTrue(expense.receipt_content)
        extraction = ReceiptExtraction.objects.get(expense=expense)
        self.assertEqual(extraction.status, ReceiptExtraction.Status.QUEUED)
        enqueue.assert_called_once_with(extraction.id)

    def test_receipt_file_is_tenant_scoped(self):
        foreign = Expense.objects.create(family=self.other_family, title="Privat", total_amount="5.00", paid_by=self.other_membership, created_by=self.outsider, receipt_content=b"secret", receipt_mime="image/jpeg")
        response = self.client.get(f"/api/expenses/{foreign.id}/receipt-file/")
        self.assertEqual(response.status_code, 404)

    def test_no_implicit_cross_currency_settlement(self):
        Expense.objects.create(family=self.family, title="EUR", total_amount="10.00", currency="EUR", paid_by=self.alex, created_by=self.user)
        summary_eur = balance_summary(self.family, "EUR")
        summary_usd = balance_summary(self.family, "USD")
        self.assertNotEqual(summary_eur[str(self.alex.id)]["balance"], summary_usd[str(self.alex.id)]["balance"])
