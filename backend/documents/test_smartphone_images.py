import io
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase
from PIL import Image
from pillow_heif import from_pillow
from pypdf import PdfWriter
from rest_framework.exceptions import ValidationError

from .images import decode_image, MAX_IMAGE_BYTES
from .storage import canonicalize_upload
from .legacy_image import canonicalize_legacy_image
from family.private_images import optimize_image
from family.profile_views import _decode_avatar


class SmartphoneImageTests(SimpleTestCase):
    def upload(self, raw, name="phone.heic"):
        return SimpleUploadedFile(name, raw, content_type="application/octet-stream")

    def heic(self):
        raw = io.BytesIO()
        from_pillow(Image.new("RGB", (900, 1200), "white")).save(raw)
        return raw.getvalue()

    def test_real_heic_decodes_through_every_image_adapter(self):
        raw = self.heic()
        document = canonicalize_upload(self.upload(raw))
        self.assertEqual(document.mime_type, "image/webp")
        private, width, height = optimize_image(self.upload(raw), max_dimension=800)
        self.assertLessEqual(max(width, height), 800)
        legacy, mime, _ = canonicalize_legacy_image(self.upload(raw))
        self.assertEqual(mime, "image/jpeg")
        self.assertEqual(_decode_avatar(self.upload(raw)).size, (900, 900))
        for content in [document.content, private, legacy]:
            with Image.open(io.BytesIO(content)) as saved:
                self.assertFalse(saved.getexif())

    def test_large_jpeg_is_bounded_and_downscaled(self):
        raw = io.BytesIO()
        Image.new("RGB", (4000, 3000), "white").save(raw, "JPEG")
        # Valid JPEG with trailing padding models a >10 MB camera input without
        # making test CPU cost depend on generating random high-entropy pixels.
        content = raw.getvalue() + b"\0" * (11 * 1024 * 1024)
        document = canonicalize_upload(self.upload(content, "phone.jpg"))
        with Image.open(io.BytesIO(document.content)) as saved:
            self.assertLessEqual(max(saved.size), 2600)
        self.assertLess(len(document.content), 1024 * 1024)

    def test_orientation_metadata_removed_and_png_webp_preserved(self):
        for fmt in ["JPEG", "PNG", "WEBP"]:
            raw = io.BytesIO()
            exif = Image.Exif(); exif[274] = 6
            Image.new("RGB", (200, 100), "white").save(raw, fmt, exif=exif)
            decoded = decode_image(raw.getvalue())
            self.assertEqual(decoded.size, (100, 200))
            self.assertFalse(decoded.getexif())

    def test_content_size_pixel_and_dimension_checks(self):
        for name in ["fake.jpg", "fake.heic", "fake.pdf"]:
            with self.assertRaises(ValidationError):
                canonicalize_upload(self.upload(b"not an image", name))
        with self.assertRaises(ValidationError):
            canonicalize_upload(self.upload(b"x" * (MAX_IMAGE_BYTES + 1)))
        raw = io.BytesIO(); Image.new("RGB", (100, 100)).save(raw, "PNG")
        with patch("documents.images.MAX_IMAGE_PIXELS", 9999):
            with self.assertRaises(ValidationError):
                canonicalize_upload(self.upload(raw.getvalue()))
        with patch("documents.images.MAX_SOURCE_DIMENSION", 99):
            with self.assertRaises(ValueError):
                decode_image(raw.getvalue())
        with self.assertRaises(ValidationError):
            canonicalize_upload(self.upload(raw.getvalue()[:50]))

    def test_pdf_bypasses_image_decoder_and_preserves_bytes(self):
        writer = PdfWriter(); writer.add_blank_page(width=100, height=100)
        raw = io.BytesIO(); writer.write(raw)
        with patch("documents.images.decode_image", side_effect=AssertionError("PDF decoded as image")):
            canonical = canonicalize_upload(self.upload(raw.getvalue(), "receipt.jpg"))
        self.assertEqual(canonical.mime_type, "application/pdf")
        self.assertEqual(canonical.content, raw.getvalue())
