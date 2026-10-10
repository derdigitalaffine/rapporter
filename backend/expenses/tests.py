import io
import uuid
from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from PIL import Image
from rest_framework.test import APIClient

from documents.models import Document, DocumentLink, DocumentProcessingRun
from family.models import Family, Membership
from .models import Expense, ExpenseShare, ReceiptExtraction
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

    def test_quick_add_accepts_local_decimal_and_safe_defaults(self):
        response = self.client.post("/api/expenses/", {
            "family": str(self.family.id),
            "title": "",
            "total_amount": "12,50",
            "currency": "EUR",
            "participants": [str(self.alex.id), str(self.sam.id)],
            "split_type": "equal",
            "client_request_id": str(uuid.uuid4()),
        }, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        expense = Expense.objects.get(id=response.data["id"])
        self.assertEqual(expense.total_amount, Decimal("12.50"))
        self.assertEqual(expense.title, "Ausgabe")
        self.assertEqual(expense.paid_by, self.alex)
        self.assertEqual(expense.source, Expense.Source.MANUAL)
        self.assertEqual(sum(expense.shares.values_list("amount", flat=True)), Decimal("12.50"))

    def test_quick_add_client_request_id_is_idempotent(self):
        request_id = str(uuid.uuid4())
        payload = {
            "family": str(self.family.id),
            "total_amount": "10.00",
            "currency": "EUR",
            "participants": [str(self.alex.id), str(self.sam.id)],
            "split_type": "equal",
            "client_request_id": request_id,
        }
        first = self.client.post("/api/expenses/", payload, format="json")
        second = self.client.post("/api/expenses/", payload, format="json")
        self.assertEqual(first.status_code, 201, first.data)
        self.assertEqual(second.status_code, 201, second.data)
        self.assertEqual(first.data["id"], second.data["id"])
        self.assertEqual(Expense.objects.filter(client_request_id=request_id).count(), 1)

    def test_quick_add_rejects_non_positive_amounts(self):
        base = {
            "family": str(self.family.id),
            "currency": "EUR",
            "participants": [str(self.alex.id), str(self.sam.id)],
            "split_type": "equal",
        }
        for value in ["0", "-1.00"]:
            response = self.client.post("/api/expenses/", {**base, "total_amount": value}, format="json")
            self.assertEqual(response.status_code, 400, response.data)

    def test_quick_add_rejects_participants_from_another_family(self):
        response = self.client.post("/api/expenses/", {
            "family": str(self.family.id),
            "total_amount": "10.00",
            "participants": [str(self.alex.id), str(self.other_membership.id)],
            "split_type": "equal",
        }, format="json")
        self.assertEqual(response.status_code, 400, response.data)

    def test_percentage_split_preserves_original_values_for_editing(self):
        payload = {
            "family": str(self.family.id),
            "title": "Brunch",
            "total_amount": "10.00",
            "currency": "EUR",
            "paid_by": str(self.alex.id),
            "participants": [str(self.alex.id), str(self.sam.id)],
            "split_type": "percentage",
            "split_values": {str(self.alex.id): "33.33", str(self.sam.id): "66.67"},
        }
        response = self.client.post("/api/expenses/", payload, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        values = {str(row["member"]): Decimal(row["split_value"]) for row in response.data["shares"]}
        self.assertEqual(values[str(self.alex.id)], Decimal("33.3300"))
        self.assertEqual(values[str(self.sam.id)], Decimal("66.6700"))

        expense_id = response.data["id"]
        payload["total_amount"] = "12.00"
        updated = self.client.patch(f"/api/expenses/{expense_id}/", payload, format="json")
        self.assertEqual(updated.status_code, 200, updated.data)
        self.assertEqual(sum(Decimal(row["amount"]) for row in updated.data["shares"]), Decimal("12.00"))
        updated_values = {str(row["member"]): Decimal(row["split_value"]) for row in updated.data["shares"]}
        self.assertEqual(updated_values, values)

    def test_settlement_changes_balance_without_creating_expense(self):
        expense = Expense.objects.create(family=self.family, title="Taxi", total_amount="20.00", currency="EUR", paid_by=self.alex, created_by=self.user)
        ExpenseShare.objects.create(expense=expense, member=self.alex, amount="10.00")
        ExpenseShare.objects.create(expense=expense, member=self.sam, amount="10.00")
        response = self.client.post("/api/expenses/settlements/", {
            "family": str(self.family.id), "from_member": str(self.sam.id), "to_member": str(self.alex.id), "amount": "10.00", "currency": "EUR"
        }, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(Expense.objects.count(), 1)
        summary = balance_summary(self.family, "EUR")
        self.assertTrue(all(row["balance"] == Decimal("0.00") for row in summary.values()))
        self.assertEqual(simplify_balances(summary), [])

        voided = self.client.post(f"/api/expenses/settlements/{response.data['id']}/void/", {}, format="json")
        self.assertEqual(voided.status_code, 200, voided.data)
        self.assertIsNotNone(voided.data["voided_at"])
        summary = balance_summary(self.family, "EUR")
        self.assertEqual(summary[str(self.alex.id)]["balance"], Decimal("10.00"))
        self.assertEqual(summary[str(self.sam.id)]["balance"], Decimal("-10.00"))

    def test_cross_family_expense_is_not_visible(self):
        foreign = Expense.objects.create(family=self.other_family, title="Privat", total_amount="5.00", paid_by=self.other_membership, created_by=self.outsider)
        response = self.client.get(f"/api/expenses/{foreign.id}/")
        self.assertEqual(response.status_code, 404)

    def test_receipt_upload_uses_private_document_queue_without_binary_copy(self):
        image = Image.new("RGB", (900, 1200), "white")
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        upload = SimpleUploadedFile("receipt.png", buffer.getvalue(), content_type="image/png")
        response = self.client.post(
            "/api/expenses/receipt/",
            {"family": str(self.family.id), "receipt": upload},
            format="multipart",
        )
        self.assertEqual(response.status_code, 202, response.data)
        expense = Expense.objects.select_related("receipt_document").get(id=response.data["id"])
        self.assertEqual(expense.status, Expense.Status.DRAFT)
        self.assertEqual(expense.receipt_status, Expense.ReceiptStatus.QUEUED)
        self.assertIsNone(expense.receipt_content)
        self.assertEqual(expense.receipt_mime, "image/webp")
        self.assertIsNotNone(expense.receipt_document_id)
        self.assertEqual(expense.receipt_document.visibility, Document.Visibility.PRIVATE)
        self.assertEqual(expense.receipt_document.kind, "receipt")
        self.assertTrue(
            DocumentLink.objects.filter(
                document=expense.receipt_document,
                domain_type=DocumentLink.DomainType.EXPENSE,
                object_id=expense.id,
                relationship="receipt",
            ).exists()
        )
        extraction = ReceiptExtraction.objects.get(expense=expense)
        self.assertEqual(extraction.status, ReceiptExtraction.Status.QUEUED)
        self.assertEqual(extraction.processing_run.document_id, expense.receipt_document_id)
        self.assertEqual(extraction.processing_run.status, DocumentProcessingRun.Status.QUEUED)

    def test_receipt_api_exposes_quality_hints_but_not_raw_ocr_evidence(self):
        expense = Expense.objects.create(
            family=self.family,
            title="Beleg",
            total_amount="7.00",
            paid_by=self.alex,
            created_by=self.user,
            source=Expense.Source.RECEIPT,
            receipt_status=Expense.ReceiptStatus.REVIEW,
            receipt_content=b"private-image",
            receipt_mime="image/jpeg",
        )
        ReceiptExtraction.objects.create(
            expense=expense,
            status=ReceiptExtraction.Status.REVIEW,
            merchant="MARKT",
            total="7.00",
            raw_text="SECRET OCR TEXT",
            error="internal detail",
            structured_data={"quality_warnings": ["dark"], "total_candidates": [{"line": "SECRET OCR TEXT"}]},
            field_confidences={"merchant": 0.8, "total": 0.9},
        )
        response = self.client.get(f"/api/expenses/{expense.id}/")
        self.assertEqual(response.status_code, 200, response.data)
        extraction = response.data["extraction"]
        self.assertEqual(extraction["quality_warnings"], ["dark"])
        self.assertNotIn("structured_data", extraction)
        self.assertNotIn("raw_text", extraction)
        self.assertNotIn("error", extraction)
        self.assertNotIn("SECRET OCR TEXT", str(response.data))

    def test_receipt_file_is_tenant_scoped(self):
        foreign = Expense.objects.create(family=self.other_family, title="Privat", total_amount="5.00", paid_by=self.other_membership, created_by=self.outsider, receipt_content=b"secret", receipt_mime="image/jpeg")
        response = self.client.get(f"/api/expenses/{foreign.id}/receipt-file/")
        self.assertEqual(response.status_code, 404)

    def test_no_implicit_cross_currency_settlement(self):
        expense = Expense.objects.create(family=self.family, title="EUR", total_amount="10.00", currency="EUR", paid_by=self.alex, created_by=self.user)
        ExpenseShare.objects.create(expense=expense, member=self.sam, amount="10.00")
        summary_eur = balance_summary(self.family, "EUR")
        summary_usd = balance_summary(self.family, "USD")
        self.assertNotEqual(summary_eur[str(self.alex.id)]["balance"], summary_usd[str(self.alex.id)]["balance"])
        self.assertEqual(summary_usd[str(self.alex.id)]["balance"], Decimal("0.00"))
