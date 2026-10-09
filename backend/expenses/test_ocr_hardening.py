from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase

from .ocr import _ocr_image, parse_receipt_text, process_receipt_extraction


class ReceiptOcrHardeningTests(TestCase):
    def test_parser_handles_european_thousands_separator(self):
        parsed = parse_receipt_text("MARKT\nTOTAL EUR 1.234,56")
        self.assertEqual(parsed["total"], Decimal("1234.56"))

    def test_parser_handles_english_thousands_separator(self):
        parsed = parse_receipt_text("MARKET\nTOTAL USD 1,234.56")
        self.assertEqual(parsed["total"], Decimal("1234.56"))

    @patch("expenses.ocr.close_old_connections")
    def test_missing_extraction_is_safe_for_worker_races(self, close_connections):
        self.assertIsNone(process_receipt_extraction("00000000-0000-0000-0000-000000000001"))
        self.assertEqual(close_connections.call_count, 2)

    @patch("expenses.ocr.pytesseract.image_to_string", return_value="ok")
    def test_ocr_timeout_is_passed_to_tesseract(self, image_to_string):
        import io
        from PIL import Image

        image = Image.new("RGB", (20, 20), "white")
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        self.assertEqual(_ocr_image(buffer.getvalue()), "ok")
        image_to_string.assert_called_once()
        self.assertEqual(image_to_string.call_args.kwargs["timeout"], 20)
