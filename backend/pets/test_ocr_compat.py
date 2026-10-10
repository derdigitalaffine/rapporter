import io
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase
from PIL import Image

from documents.legacy_image_ocr import normalize_image_upload, ocr_image_content
from pets import ocr as pet_ocr


class PetOcrCompatibilityTests(SimpleTestCase):
    def image_upload(self, *, size=(800, 800), color="white"):
        output = io.BytesIO()
        Image.new("RGB", size, color).save(output, format="PNG")
        return SimpleUploadedFile("pet.png", output.getvalue(), content_type="image/png")

    def test_pet_generic_image_helpers_are_owned_by_documents(self):
        self.assertIs(pet_ocr.normalize_image_upload, normalize_image_upload)
        self.assertIs(pet_ocr._ocr_image, ocr_image_content)
        self.assertEqual(pet_ocr.parse_receipt_text.__module__, "expenses.ocr")

    def test_legacy_normalization_contract_stays_compatible_for_pet_uploads(self):
        content, content_type, warnings = normalize_image_upload(
            self.image_upload(size=(600, 600), color="black")
        )
        self.assertEqual(content_type, "image/jpeg")
        self.assertIn("low_resolution", warnings)
        self.assertIn("dark", warnings)
        with Image.open(io.BytesIO(content)) as decoded:
            self.assertEqual(decoded.format, "JPEG")
            self.assertEqual(decoded.mode, "RGB")

    def test_pet_worker_ocr_patch_seam_still_works(self):
        with patch("pets.ocr._ocr_image", return_value="Tollwutimpfung 12.03.2026") as mocked:
            text = pet_ocr._ocr_image(b"not-decoded-because-mocked")
        self.assertEqual(text, "Tollwutimpfung 12.03.2026")
        mocked.assert_called_once()
