import io
from hashlib import sha256
from unittest.mock import patch

from django.test import SimpleTestCase
from PIL import Image, ImageEnhance, ImageOps

from .ocr import UploadAdapter, _ocr_image, extract_pet_fields, prepare_pet_upload


class PetDocumentCoreBridgeTests(SimpleTestCase):
    def image_bytes(self):
        output = io.BytesIO()
        Image.new("RGB", (900, 1200), "white").save(output, "PNG")
        return output.getvalue()

    def legacy_normalized_bytes(self, raw):
        image = Image.open(io.BytesIO(raw))
        image = ImageOps.exif_transpose(image).convert("RGB")
        image.thumbnail((2500, 2500), Image.Resampling.LANCZOS)
        image = ImageEnhance.Contrast(image).enhance(1.08)
        output = io.BytesIO()
        image.save(output, format="JPEG", quality=88, optimize=True)
        return output.getvalue()

    def test_pet_image_upload_preserves_legacy_duplicate_hash_contract(self):
        raw = self.image_bytes()
        prepared = prepare_pet_upload(UploadAdapter(raw, "pet.png", "image/png"))
        expected = self.legacy_normalized_bytes(raw)

        self.assertEqual(prepared["content_type"], "image/jpeg")
        self.assertEqual(prepared["content"], expected)
        self.assertEqual(prepared["sha256"], sha256(expected).hexdigest())

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
