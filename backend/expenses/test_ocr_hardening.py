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
        self.assertEqual(parsed["currency"], "USD")

    def test_structured_receipt_extracts_time_tax_subtotal_id_and_items(self):
        parsed = parse_receipt_text(
            "\n".join(
                [
                    "EDEKA MUSTERMANN",
                    "Musterstr. 1",
                    "Beleg-Nr. 4711",
                    "Datum 16.10.2026 18:42",
                    "Milch 1,49",
                    "Brot 2,50",
                    "Netto 3,35",
                    "MwSt 19% 0,64",
                    "GESAMT EUR 3,99",
                    "Karte 10,00",
                    "Rückgeld 6,01",
                ]
            ),
            ocr_confidence=0.88,
        )
        self.assertEqual(parsed["merchant"], "EDEKA MUSTERMANN")
        self.assertEqual(parsed["date"].isoformat(), "2026-10-16")
        self.assertEqual(parsed["time"].isoformat(), "18:42:00")
        self.assertEqual(parsed["total"], Decimal("3.99"))
        self.assertEqual(parsed["subtotal"], Decimal("3.35"))
        self.assertEqual(parsed["tax"], Decimal("0.64"))
        self.assertEqual(parsed["receipt_id"], "4711")
        self.assertEqual(parsed["currency"], "EUR")
        self.assertEqual(len(parsed["structured_data"]["line_items"]), 2)
        self.assertEqual(parsed["structured_data"]["reconciliation"]["status"], "matched")
        self.assertEqual(parsed["structured_data"]["schema_version"], 2)
        self.assertEqual(parsed["structured_data"]["extractor_version"], "receipt-v2")

    def test_total_beats_tender_change_tax_and_phone_numbers(self):
        parsed = parse_receipt_text(
            "\n".join(
                [
                    "REWE TESTMARKT",
                    "Tel. 0631 12,34",
                    "MwSt 19% 1,90",
                    "GESAMT € 11,90",
                    "Gegeben 50,00",
                    "Karte 50,00",
                    "Rückgeld 38,10",
                ]
            )
        )
        self.assertEqual(parsed["total"], Decimal("11.90"))
        self.assertGreater(parsed["field_confidences"]["total"], 0.8)
        self.assertTrue(any("payment:" in " ".join(item["reasons"]) for item in parsed["structured_data"]["total_candidates"]))

    def test_competing_total_labels_reduce_confidence_and_force_review(self):
        parsed = parse_receipt_text("MARKT\nSUMME 12,34\nGESAMT 12,44")
        self.assertIn(parsed["total"], {Decimal("12.34"), Decimal("12.44")})
        self.assertIn("total_ambiguous", parsed["review_reasons"])
        self.assertTrue(parsed["needs_review"])
        self.assertLess(parsed["field_confidences"]["total"], 0.8)

    def test_invalid_date_is_discarded_but_iso_date_is_supported(self):
        invalid = parse_receipt_text("MARKT\nDatum 31.02.2026\nTOTAL EUR 1,00")
        valid = parse_receipt_text("MARKT\n2026-10-16 09:07\nTOTAL EUR 1,00")
        self.assertIsNone(invalid["date"])
        self.assertEqual(valid["date"].isoformat(), "2026-10-16")
        self.assertEqual(valid["time"].isoformat(), "09:07:00")

    def test_currency_is_not_invented_without_explicit_signal(self):
        parsed = parse_receipt_text("MARKT\nGESAMT 12,34")
        self.assertEqual(parsed["currency"], "")
        self.assertEqual(parsed["field_confidences"]["currency"], 0.0)

    def test_line_items_exclude_summary_tax_payment_and_footer_lines(self):
        parsed = parse_receipt_text(
            "MARKT\nApfel 1,20\n2 x 1,50 Wasser 3,00\nMwSt 0,67\nSUMME EUR 4,20\nKarte 4,20\nTel. 12,34"
        )
        items = parsed["structured_data"]["line_items"]
        self.assertEqual([item["total"] for item in items], ["1.20", "3.00"])
        self.assertEqual(items[1]["quantity"], "2")
        self.assertEqual(items[1]["unit_price"], "1.50")

    def test_reconciliation_mismatch_never_changes_values(self):
        parsed = parse_receipt_text(
            "MARKT\nArtikel 3,99\nNetto 3,00\nMwSt 0,50\nGESAMT EUR 3,99",
            ocr_confidence=0.9,
        )
        self.assertEqual(parsed["subtotal"], Decimal("3.00"))
        self.assertEqual(parsed["tax"], Decimal("0.50"))
        self.assertEqual(parsed["total"], Decimal("3.99"))
        self.assertEqual(parsed["structured_data"]["reconciliation"]["status"], "mismatch")
        self.assertIn("reconciliation_mismatch", parsed["review_reasons"])

    def test_low_ocr_confidence_is_separate_from_semantic_confidence(self):
        parsed = parse_receipt_text("MARKT\nGESAMT EUR 12,34", ocr_confidence=0.31)
        self.assertEqual(parsed["total"], Decimal("12.34"))
        self.assertGreater(parsed["field_confidences"]["total"], 0.8)
        self.assertEqual(parsed["structured_data"]["ocr_confidence"], 0.31)
        self.assertIn("ocr_confidence_low", parsed["review_reasons"])

    def test_expense_module_no_longer_owns_generic_ocr_or_worker_execution(self):
        self.assertFalse(hasattr(ocr, "_ocr_image"))
        self.assertFalse(hasattr(ocr, "normalize_receipt_upload"))
        self.assertFalse(hasattr(ocr, "process_receipt_extraction"))
        self.assertFalse(hasattr(ocr, "enqueue_receipt_extraction"))
