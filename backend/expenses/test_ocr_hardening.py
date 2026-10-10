from decimal import Decimal

from django.test import SimpleTestCase

from . import ocr
from .ocr import parse_receipt_text


class ReceiptParserHardeningTests(SimpleTestCase):
    def test_parser_handles_european_thousands_separator(self):
        parsed = parse_receipt_text("MARKT\nTOTAL EUR 1.234,56")
        self.assertEqual(parsed["total"], Decimal("1234.56"))

    def test_parser_handles_english_thousands_separator(self):
        parsed = parse_receipt_text("MARKET\nTOTAL USD 1,234.56")
        self.assertEqual(parsed["total"], Decimal("1234.56"))

    def test_expense_module_no_longer_owns_generic_ocr_or_worker_execution(self):
        self.assertFalse(hasattr(ocr, "_ocr_image"))
        self.assertFalse(hasattr(ocr, "normalize_receipt_upload"))
        self.assertFalse(hasattr(ocr, "process_receipt_extraction"))
        self.assertFalse(hasattr(ocr, "enqueue_receipt_extraction"))
