import io
from unittest.mock import patch

from django.test import SimpleTestCase
from PIL import Image

from .ocr import UploadAdapter, _ocr_image, extract_pet_fields, prepare_pet_upload


class PetDocumentCoreBridgeTests(SimpleTestCase):
    def image_bytes(self):
        output = io.BytesIO()
        Image.new("RGB", (900, 1200), "white").save(output, "PNG")
        return output.getvalue()

    def test_pet_image_upload_uses_document_canonicalization(self):
        raw = self.image_bytes()
        prepared = prepare_pet_upload(UploadAdapter(raw, "pet.png", "image/png"))

        self.assertEqual(prepared["content_type"], "image/webp")
        self.assertTrue(prepared["content"])
        self.assertEqual(len(prepared["sha256"]), 64)

    def test_pet_ocr_compatibility_name_delegates_to_document_core(self):
        with patch("pets.ocr.extract_legacy_image_text", return_value="Tierarzt Rechnung") as shared:
            text = _ocr_image(b"image")
        self.assertEqual(text, "Tierarzt Rechnung")
        shared.assert_called_once_with(b"image")

    def test_pet_invoice_suggestions_do_not_depend_on_expense_receipt_parser(self):
        result = extract_pet_fields(
            "Tierarztpraxis Muster\nRechnung\nRechnungsdatum: 10.10.2026\nGesamt: 123,45 EUR"
        )
        self.assertEqual(result["kind"], "invoice")
        self.assertEqual(result["fields"]["total"], "123.45")
        self.assertEqual(result["fields"]["occurred_at"], "2026-10-10")
        self.assertEqual(result["fields"]["provider_name"], "Tierarztpraxis Muster")
