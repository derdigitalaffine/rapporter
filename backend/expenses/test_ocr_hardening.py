from decimal import Decimal

from django.test import TestCase

from .ocr import parse_receipt_text


class ReceiptParserHardeningTests(TestCase):
    def test_parser_handles_european_thousands_separator(self):
        parsed = parse_receipt_text("MARKT\nTOTAL EUR 1.234,56")
        self.assertEqual(parsed["total"], Decimal("1234.56"))

    def test_parser_handles_english_thousands_separator(self):
        parsed = parse_receipt_text("MARKET\nTOTAL USD 1,234.56")
        self.assertEqual(parsed["total"], Decimal("1234.56"))

    def test_parser_does_not_treat_change_as_total(self):
        parsed = parse_receipt_text("MARKT\nSUMME EUR 12,34\nRÜCKGELD 7,66")
        self.assertEqual(parsed["total"], Decimal("12.34"))
