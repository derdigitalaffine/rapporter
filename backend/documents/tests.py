import io
import json
import tempfile
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.storage import FileSystemStorage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import models
from django.test import TestCase
from PIL import Image
from pypdf import PdfWriter
from rest_framework.test import APIClient

from family.models import Family, Membership

from .models import Document


class DocumentCoreTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.alice = User.objects.create_user(username="doc-alice", password="test-pass-123")
        self.bob = User.objects.create_user(username="doc-bob", password="test-pass-123")
        self.cara = User.objects.create_user(username="doc-cara", password="test-pass-123")
        self.outsider = User.objects.create_user(username="doc-outsider", password="test-pass-123")
        self.family = Family.objects.create(name="Document Family", slug="document-family")
        self.other_family = Family.objects.create(name="Other Document Family", slug="other-document-family")
        self.alice_member = Membership.objects.create(family=self.family, user=self.alice, role=Membership.Role.OWNER, display_name="Alice")
        self.bob_member = Membership.objects.create(family=self.family, user=self.bob, role=Membership.Role.ADULT, display_name="Bob")
        self.cara_member = Membership.objects.create(family=self.family, user=self.cara, role=Membership.Role.ADULT, display_name="Cara")
        self.outsider_member = Membership.objects.create(family=self.other_family, user=self.outsider, role=Membership.Role.OWNER, display_name="Outsider")
        self.client = APIClient()
        self.tmp = tempfile.TemporaryDirectory()
        self.storage_patch = patch("documents.storage.default_storage", FileSystemStorage(location=self.tmp.name))
        self.storage_patch.start()

    def tearDown(self):
        self.storage_patch.stop()
        self.tmp.cleanup()

    def auth(self, user):
        self.client.force_authenticate(user)

    def pdf_bytes(self):
        output = io.BytesIO()
        writer = PdfWriter()
        writer.add_blank_page(width=200, height=200)
        writer.add_metadata({"/FamilyOSTest": "signature-safe-canonical"})
        writer.write(output)
        return output.getvalue()

    def image_bytes(self):
        output = io.BytesIO()
        image = Image.new("RGB", (100, 80), "white")
        image.save(output, "JPEG", quality=95)
        return output.getvalue()

    def upload(self, user=None, content=None, name="source.bin", **fields):
        self.auth(user or self.alice)
        payload = {
            "family": str(fields.pop("family", self.family.id)),
            "title": fields.pop("title", "Testdokument"),
            "visibility": fields.pop("visibility", "private"),
            "file": SimpleUploadedFile(name, content or self.pdf_bytes(), content_type="application/octet-stream"),
            **fields,
        }
        return self.client.post("/api/documents/", payload, format="multipart")

    def test_private_family_and_selected_acl_are_enforced_server_side(self):
        private = self.upload(visibility="private")
        self.assertEqual(private.status_code, 201)
        private_id = private.data["id"]

        self.auth(self.bob)
        self.assertEqual(self.client.get(f"/api/documents/{private_id}/").status_code, 404)
        self.assertEqual(self.client.get(f"/api/documents/{private_id}/file/").status_code, 404)

        # This test exercises ACL semantics, not dedupe; identical fixture bytes are
        # therefore explicitly accepted as separate documents.
        family_doc = self.upload(visibility="family", title="Familie", allow_duplicate="true")
        self.assertEqual(family_doc.status_code, 201)
        self.auth(self.bob)
        self.assertEqual(self.client.get(f"/api/documents/{family_doc.data['id']}/").status_code, 200)

        selected = self.upload(
            visibility="selected",
            title="Ausgewählt",
            allow_duplicate="true",
            access=json.dumps([{"membership": str(self.bob_member.id), "can_view": True}]),
        )
        self.assertEqual(selected.status_code, 201)
        self.auth(self.bob)
        self.assertEqual(self.client.get(f"/api/documents/{selected.data['id']}/").status_code, 200)
        self.auth(self.cara)
        self.assertEqual(self.client.get(f"/api/documents/{selected.data['id']}/").status_code, 404)

    def test_guessed_cross_family_document_id_returns_404(self):
        response = self.upload(visibility="family")
        self.auth(self.outsider)
        self.assertEqual(self.client.get(f"/api/documents/{response.data['id']}/").status_code, 404)
        self.assertEqual(self.client.get(f"/api/documents/{response.data['id']}/file/").status_code, 404)

    def test_content_detection_ignores_extension_and_private_download_is_no_store(self):
        raw = self.pdf_bytes()
        response = self.upload(content=raw, name="looks-like-an-image.jpg", visibility="family")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["mime_type"], "application/pdf")
        self.assertNotIn("looks-like-an-image", Document.objects.get(id=response.data["id"]).canonical_file)

        file_response = self.client.get(f"/api/documents/{response.data['id']}/file/")
        self.assertEqual(file_response.status_code, 200)
        self.assertEqual(file_response["Cache-Control"], "private, no-store")
        self.assertEqual(file_response["X-Content-Type-Options"], "nosniff")
        self.assertEqual(b"".join(file_response.streaming_content), raw)

    def test_pdf_is_preserved_byte_for_byte_so_existing_signatures_are_not_broken(self):
        raw = self.pdf_bytes()
        response = self.upload(content=raw, name="signed.pdf")
        self.assertEqual(response.status_code, 201)
        file_response = self.client.get(f"/api/documents/{response.data['id']}/file/")
        self.assertEqual(b"".join(file_response.streaming_content), raw)

    def test_images_are_normalized_to_metadata_free_webp(self):
        response = self.upload(content=self.image_bytes(), name="camera.jpg")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["mime_type"], "image/webp")
        document = Document.objects.get(id=response.data["id"])
        self.assertTrue(document.canonical_file.endswith(".webp"))
        file_response = self.client.get(f"/api/documents/{document.id}/file/")
        normalized = b"".join(file_response.streaming_content)
        with Image.open(io.BytesIO(normalized)) as image:
            self.assertEqual(image.format, "WEBP")
            self.assertFalse(image.getexif())

    def test_duplicate_warning_can_be_overridden_without_leaking_private_documents(self):
        raw = self.pdf_bytes()
        first = self.upload(content=raw)
        duplicate = self.upload(content=raw)
        self.assertEqual(duplicate.status_code, 409)
        self.assertEqual(duplicate.data["code"], "duplicate_document")
        self.assertEqual(duplicate.data["existing_document_id"], first.data["id"])

        allowed = self.upload(content=raw, allow_duplicate="true")
        self.assertEqual(allowed.status_code, 201)
        self.assertNotEqual(allowed.data["id"], first.data["id"])

        # Bob possesses identical bytes but cannot see Alice's private document.
        # Creating his own copy must not reveal that Alice already stored it.
        bob_copy = self.upload(user=self.bob, content=raw)
        self.assertEqual(bob_copy.status_code, 201)

    def test_archive_restore_and_purge_have_explicit_lifecycle(self):
        response = self.upload(visibility="family")
        document_id = response.data["id"]
        document = Document.objects.get(id=document_id)
        stored = document.canonical_file

        self.assertEqual(self.client.post(f"/api/documents/{document_id}/purge/").status_code, 409)
        self.assertEqual(self.client.delete(f"/api/documents/{document_id}/").status_code, 204)
        listed = self.client.get(f"/api/documents/?family={self.family.id}")
        self.assertEqual(listed.status_code, 200)
        self.assertFalse(any(row["id"] == document_id for row in listed.data))
        self.assertEqual(self.client.post(f"/api/documents/{document_id}/restore/").status_code, 200)
        self.assertIsNone(Document.objects.get(id=document_id).archived_at)

        self.client.delete(f"/api/documents/{document_id}/")
        self.assertEqual(self.client.post(f"/api/documents/{document_id}/purge/").status_code, 204)
        self.assertFalse(Document.objects.filter(id=document_id).exists())
        from documents.storage import default_storage
        self.assertFalse(default_storage.exists(stored))

    def test_domain_links_are_typed_and_access_management_stays_same_family(self):
        object_id = "11111111-1111-1111-1111-111111111111"
        response = self.upload(
            visibility="selected",
            access=json.dumps([{"membership": str(self.bob_member.id), "can_manage": True}]),
            links=json.dumps([{"domain_type": "expense", "object_id": object_id, "relationship": "receipt"}]),
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["links"][0]["domain_type"], "expense")
        self.assertEqual(response.data["links"][0]["object_id"], object_id)

        self.auth(self.bob)
        patch_response = self.client.patch(
            f"/api/documents/{response.data['id']}/",
            {"title": "Von Bob verwaltet"},
            format="json",
        )
        self.assertEqual(patch_response.status_code, 200)

        self.auth(self.alice)
        invalid = self.client.patch(
            f"/api/documents/{response.data['id']}/",
            {"access": [{"membership": str(self.outsider_member.id), "can_view": True}]},
            format="json",
        )
        self.assertEqual(invalid.status_code, 400)

    def test_document_core_never_uses_binaryfield_for_canonical_file(self):
        field = Document._meta.get_field("canonical_file")
        self.assertIsInstance(field, models.CharField)
        self.assertNotIsInstance(field, models.BinaryField)

    def test_invalid_file_is_rejected(self):
        response = self.upload(content=b"not a supported file", name="malware.pdf")
        self.assertEqual(response.status_code, 400)
