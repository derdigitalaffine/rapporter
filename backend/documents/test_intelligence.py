from unittest.mock import patch

from django.test import SimpleTestCase
from PIL import Image

from .extraction import ExtractionResult, _ocr_image
from .intelligence import classify_result, enrich_extraction
from .quality import assess_image, prepare_for_ocr


def result_for(text, *, needs_review=True):
    return ExtractionResult(
        text=text,
        extractor="fixture",
        fields=[
            {
                "key": "text.page",
                "value_json": {"text": text, "source": "fixture"},
                "confidence": 1.0,
                "page": 1,
                "bbox": None,
                "evidence_text": text,
                "source_type": "explicit",
            }
        ],
        needs_review=needs_review,
    )


class DocumentIntelligenceTests(SimpleTestCase):
    def test_classifier_covers_registered_document_types_with_synthetic_fixtures(self):
        fixtures = {
            "receipt": "Kassenbon\nKasse 2\nBon-Nr: A123\nRückgeld 3,00 EUR",
            "invoice": "Rechnung\nRechnungsnummer: RE-2026-0042\nNetto 100,00\nBrutto 119,00 EUR",
            "contract": "Vertrag\nVertragsnummer: V-42\nVertragsbeginn: 10.10.2026\nLaufzeit 12 Monate",
            "official_letter": "Bescheid\nAktenzeichen: AZ-42/2026\nSachbearbeiter: Beispiel",
            "warranty": "Garantie\nSeriennummer: SN-4242\nGarantiezeit 24 Monate",
            "school": "Elternbrief der Schule\nSchuljahr 2026/27\nKlasse: 4b",
            "medical": "Arztpraxis Muster\nPatient\nImpfung\nImpfdatum: 10.10.2026",
            "pet": "Tierarzt\nHeimtierausweis\nChipnummer: DE-424242",
            "identity": "Personalausweis\nAusweisnummer: L01X00T47\nGültig bis: 10.10.2030",
        }
        for expected, text in fixtures.items():
            with self.subTest(expected=expected):
                classification = classify_result(result_for(text))
                self.assertEqual(classification.kind, expected)
                self.assertGreaterEqual(classification.confidence, 0.65)

    def test_invoice_fields_have_page_evidence_confidence_and_source(self):
        result = enrich_extraction(
            result_for(
                "Rechnung\n"
                "Rechnungsnummer: RE-2026-0042\n"
                "Rechnungsdatum: 10.10.2026\n"
                "Gesamt: 1.234,56 EUR"
            )
        )
        fields = {field["key"]: field for field in result.fields if field["key"] != "text.page"}
        self.assertEqual(fields["document.type"]["value_json"]["value"], "invoice")
        self.assertEqual(fields["invoice.number"]["value_json"]["value"], "RE-2026-0042")
        self.assertEqual(fields["document.date"]["value_json"]["value"], "10.10.2026")
        self.assertEqual(fields["amount.total"]["value_json"]["value"], "1.234,56")
        for key in ("invoice.number", "document.date", "amount.total"):
            self.assertEqual(fields[key]["page"], 1)
            self.assertTrue(fields[key]["evidence_text"])
            self.assertEqual(fields[key]["source_type"], "explicit")
            self.assertGreater(float(fields[key]["confidence"]), 0.9)
            self.assertEqual(fields[key]["extractor_version"], "rules-v1")

    def test_concrete_born_digital_suggestions_stay_in_review(self):
        invoice = enrich_extraction(
            result_for(
                "Rechnung\nRechnungsnummer: RE-2026-0042\nGesamt: 42,00 EUR",
                needs_review=False,
            )
        )
        self.assertTrue(invoice.needs_review)
        self.assertEqual(invoice.quality_data["classification"]["kind"], "invoice")

        generic = enrich_extraction(
            result_for("Familiennotiz ohne strukturierten Dokumenttyp", needs_review=False)
        )
        self.assertFalse(generic.needs_review)
        self.assertEqual(generic.quality_data["classification"]["kind"], "generic")

    def test_unlabelled_numbers_do_not_become_amount_or_deadline_fields(self):
        result = enrich_extraction(
            result_for("Kurze Notiz\nTelefon 0621 123456\nTreffen irgendwann im Oktober\nWert 123,45")
        )
        keys = {field["key"] for field in result.fields}
        self.assertEqual(result.quality_data["classification"]["kind"], "generic")
        self.assertNotIn("amount.total", keys)
        self.assertNotIn("document.date", keys)

    def test_quality_metrics_are_content_agnostic_and_preprocessing_is_transient(self):
        source = Image.new("RGB", (320, 480), "black")
        metrics = assess_image(source)
        self.assertEqual(metrics["width"], 320)
        self.assertIn("low_resolution", metrics["warnings"])
        self.assertIn("dark", metrics["warnings"])

        prepared, quality = prepare_for_ocr(source)
        self.assertEqual(source.mode, "RGB")
        self.assertEqual(source.size, (320, 480))
        self.assertEqual(prepared.mode, "L")
        self.assertIn("deskew_degrees", quality["preprocessing"])
        self.assertFalse(quality["preprocessing"]["destructive_thresholding"])

    def test_weak_tall_layout_tries_alternative_psm_and_selects_better_result(self):
        image = Image.new("RGB", (200, 600), "white")
        weak = {
            "text": ["x"],
            "conf": ["20"],
            "left": [10],
            "top": [10],
            "width": [10],
            "height": [10],
            "block_num": [1],
            "par_num": [1],
            "line_num": [1],
        }
        strong = {
            "text": ["Gesamt", "42,00"],
            "conf": ["95", "93"],
            "left": [10, 80],
            "top": [10, 10],
            "width": [60, 50],
            "height": [20, 20],
            "block_num": [1, 1],
            "par_num": [1, 1],
            "line_num": [1, 1],
        }
        with patch("documents.extraction.pytesseract.image_to_data", side_effect=[weak, strong]) as ocr:
            page = _ocr_image(image, 1, heartbeat=lambda: None)
        self.assertEqual(ocr.call_count, 2)
        self.assertEqual(page["psm"], 4)
        self.assertEqual(page["text"], "Gesamt 42,00")
        self.assertEqual([item["psm"] for item in page["psm_candidates"]], [6, 4])
        self.assertGreater(page["confidence"], 0.9)
