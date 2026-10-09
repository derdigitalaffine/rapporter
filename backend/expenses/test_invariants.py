from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from family.models import Family, Membership
from .models import Expense, ExpenseShare, ReceiptExtraction, Settlement
from .serializers import ExpenseSerializer

User = get_user_model()


class ExpenseInvariantApiTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="alex", password="test")
        self.other = User.objects.create_user(username="sam", password="test")
        self.family = Family.objects.create(name="Familie", slug="familie-invariants")
        self.other_family = Family.objects.create(name="Andere", slug="andere-invariants")
        self.alex = Membership.objects.create(family=self.family, user=self.user, role=Membership.Role.OWNER, display_name="Alex")
        self.sam = Membership.objects.create(family=self.family, user=self.other, role=Membership.Role.ADULT, display_name="Sam")
        self.alex_other = Membership.objects.create(family=self.other_family, user=self.user, role=Membership.Role.OWNER, display_name="Alex")
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_posted_expense_cannot_be_reparented_to_another_family(self):
        expense = Expense.objects.create(
            family=self.family,
            title="Einkauf",
            total_amount="10.00",
            currency="EUR",
            paid_by=self.alex,
            created_by=self.user,
        )
        ExpenseShare.objects.create(expense=expense, member=self.alex, amount="10.00")
        response = self.client.patch(
            f"/api/expenses/{expense.id}/",
            {
                "family": str(self.other_family.id),
                "paid_by": str(self.alex_other.id),
                "participants": [str(self.alex_other.id)],
                "split_type": "equal",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400, response.data)
        expense.refresh_from_db()
        self.assertEqual(expense.family_id, self.family.id)
        self.assertEqual(expense.shares.get().member_id, self.alex.id)

    def test_settlement_cannot_exceed_current_debt(self):
        expense = Expense.objects.create(
            family=self.family,
            title="Taxi",
            total_amount="20.00",
            currency="EUR",
            paid_by=self.alex,
            created_by=self.user,
        )
        ExpenseShare.objects.create(expense=expense, member=self.alex, amount="10.00")
        ExpenseShare.objects.create(expense=expense, member=self.sam, amount="10.00")
        response = self.client.post(
            "/api/expenses/settlements/",
            {
                "family": str(self.family.id),
                "from_member": str(self.sam.id),
                "to_member": str(self.alex.id),
                "amount": "10.01",
                "currency": "EUR",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400, response.data)
        self.assertEqual(Settlement.objects.count(), 0)
        self.assertIn("10.00 EUR", str(response.data))

    def test_receipt_delete_removes_private_extraction_and_resets_status(self):
        expense = Expense.objects.create(
            family=self.family,
            title="Beleg",
            total_amount="7.00",
            currency="EUR",
            paid_by=self.alex,
            created_by=self.user,
            source=Expense.Source.RECEIPT,
            receipt_content=b"private-image",
            receipt_mime="image/jpeg",
            receipt_status=Expense.ReceiptStatus.READY,
        )
        extraction = ReceiptExtraction.objects.create(
            expense=expense,
            status=ReceiptExtraction.Status.READY,
            raw_text="SECRET OCR TEXT",
            structured_data={"quality_warnings": ["dark"], "total_candidates": [{"line": "SECRET OCR TEXT"}]},
        )
        extraction_id = extraction.id
        response = self.client.delete(f"/api/expenses/{expense.id}/receipt-file/")
        self.assertEqual(response.status_code, 204)
        expense.refresh_from_db()
        self.assertIsNone(expense.receipt_content)
        self.assertEqual(expense.receipt_mime, "")
        self.assertEqual(expense.receipt_status, Expense.ReceiptStatus.NONE)
        self.assertFalse(ReceiptExtraction.objects.filter(id=extraction_id).exists())

    def test_serializer_does_not_load_deferred_receipt_blob(self):
        expense = Expense.objects.create(
            family=self.family,
            title="Beleg",
            total_amount="7.00",
            currency="EUR",
            paid_by=self.alex,
            created_by=self.user,
            receipt_content=b"private-image",
            receipt_mime="image/jpeg",
        )
        expense = Expense.objects.select_related("paid_by", "paid_by__user", "created_by").defer("receipt_content").get(id=expense.id)
        self.assertIn("receipt_content", expense.get_deferred_fields())
        data = ExpenseSerializer(expense).data
        self.assertTrue(data["receipt_available"])
        self.assertIn("receipt_content", expense.get_deferred_fields())

    def test_valid_partial_settlement_remains_allowed(self):
        expense = Expense.objects.create(
            family=self.family,
            title="Taxi",
            total_amount="20.00",
            currency="EUR",
            paid_by=self.alex,
            created_by=self.user,
        )
        ExpenseShare.objects.create(expense=expense, member=self.alex, amount="10.00")
        ExpenseShare.objects.create(expense=expense, member=self.sam, amount="10.00")
        response = self.client.post(
            "/api/expenses/settlements/",
            {
                "family": str(self.family.id),
                "from_member": str(self.sam.id),
                "to_member": str(self.alex.id),
                "amount": "4.25",
                "currency": "EUR",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(Settlement.objects.get().amount, Decimal("4.25"))
