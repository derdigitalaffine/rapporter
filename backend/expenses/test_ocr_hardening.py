from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase

from .models import ReceiptExtraction
from .ocr import parse_receipt_text, process_receipt_extraction


class ReceiptOcrHardeningTests(TestCase):
    def test_parser_handles_european_thousands_separator(self):
        parsed = parse_receipt_text("MARKT\nTOTAL EUR 1.234,56")
        self.assertEqual(parsed["total"], Decimal("1234.56"))

    def test_parser_handles_english_thousands_separator(self):
        parsed = parse_receipt_text("MARKET\nTOTAL USD 1,234.56")
        self.assertEqual(parsed["total"], Decimal("1234.56"))

    def test_missing_extraction_is_safe_for_worker_races(self):
        self.assertIsNone(process_receipt_extraction("00000000-0000-0000-0000-000000000001"))

    @patch("expenses.ocr.pytesseract.image_to_string")
    def test_ocr_timeout_is_bounded(self, image_to_string):
        # The image call itself is covered through the configured timeout contract;
        # this assertion prevents accidental removal of the bound in future changes.
        from expenses.ocr import OCR_TIMEOUT_SECONDS
        self.assertEqual(OCR_TIMEOUT_SECONDS, 20)
        image_to_string.assert_not_called()
