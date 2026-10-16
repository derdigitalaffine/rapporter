from decimal import Decimal

from django.test import SimpleTestCase

from .document_receipts import _receipt_ocr_confidence
from .models import ReceiptExtraction
from .serializers import ReceiptExtractionSerializer


class ReceiptIntelligenceContractTests(SimpleTestCase):
    def test_page_ocr_confidence_is_bounded_and_averaged(self):
        quality = {"pages": [{"confidence": 0.9}, {"confidence": 0.7}, {"confidence": 4.0}, {"confidence": "bad"}]}
        self.assertEqual(_receipt_ocr_confidence(quality), 0.8667)
        self.assertIsNone(_receipt_ocr_confidence({"pages": [{"quality": {"warnings": ["dark"]}}]}))

    def test_serializer_exposes_only_bounded_v2_intelligence(self):
        extraction = ReceiptExtraction(
            status=ReceiptExtraction.Status.REVIEW,
            merchant="REWE MARKT",
            total=Decimal("12.34"),
            subtotal=Decimal("11.53"),
            tax=Decimal("0.81"),
            currency="EUR",
            parser_version="receipt-v2",
            field_confidences={"total": 0.91},
            structured_data={
                "schema_version": 2,
                "extractor_version": "receipt-v2",
                "ocr_confidence": 0.84,
                "semantic_confidence": 0.88,
                "fields": {"total": {"raw": "SUMME 12,34", "normalized": "12.34"}},
                "total_candidates": [{"amount": "12.34", "score": 0.91, "line": "SUMME 12,34"}],
                "line_items": [{"description": "MILCH", "total": "1.29"}],
                "reconciliation": {"status": "partial", "item_sum": "1.29", "checks": []},
                "review": {"needs_review": True, "reasons": ["total_ambiguous"]},
                "quality_warnings": ["dark"],
                "internal_debug": {"must_not_leak": True},
            },
        )

        data = ReceiptExtractionSerializer(extraction).data

        self.assertEqual(data["subtotal"], "11.53")
        self.assertEqual(data["tax"], "0.81")
        self.assertEqual(data["structured_data"]["schema_version"], 2)
        self.assertEqual(data["structured_data"]["line_items"][0]["description"], "MILCH")
        self.assertNotIn("internal_debug", data["structured_data"])
        self.assertNotIn("quality_warnings", data["structured_data"])
        self.assertEqual(data["quality_warnings"], ["dark"])

    def test_legacy_structured_data_stays_hidden_from_v2_ui_contract(self):
        extraction = ReceiptExtraction(
            status=ReceiptExtraction.Status.REVIEW,
            structured_data={"total_candidates": [{"amount": "9.99"}], "quality_warnings": []},
        )
        data = ReceiptExtractionSerializer(extraction).data
        self.assertEqual(data["structured_data"], {})
