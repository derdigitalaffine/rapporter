import hashlib
import io
import json
import zipfile
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from rest_framework.test import APIClient

from telemetry.models import AuditEvent

from .shopping_reference_models import ReferenceDataset
from .shopping_reference_validation import reference_content_checksum


class ShoppingReferenceOperatorTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.admin = User.objects.create_user(username="dataset-admin", password="unused", is_superuser=True, is_staff=True)
        self.member = User.objects.create_user(username="dataset-member", password="unused")
        self.client = APIClient()

    def _package(self, *, dataset_id="shopping.de.lexicon.operator-test", version="1", redistribution="adopt"):
        payload = {"lexicon.json": json.dumps({"entries": [{"id": "food.milk", "label_de": "Milch", "aliases": ["Vollmilch"]}]}).encode()}
        manifest = {
            "schema_version": 1,
            "dataset_id": dataset_id,
            "dataset_type": "lexicon",
            "version": version,
            "source_url": "https://example.test/reference/lexicon",
            "source_revision": "fixture-1",
            "locale": "de-DE",
            "country": "DE",
            "licence": "CC0-1.0" if redistribution != "defer" else "unknown pending review",
            "attribution": "Fixture authors",
            "redistribution": redistribution,
            "checksum": reference_content_checksum(payload),
            "coverage": {"completeness_claim": False},
            "quality": {"ambiguous_input_policy": "ABSTAIN"},
            "dependencies": [],
            "privacy": {
                "contains_private_household_data": False,
                "contains_user_or_family_ids": False,
                "contains_private_family_corrections": False,
                "contains_household_observations": False,
            },
            "files": [
                {
                    "path": "lexicon.json",
                    "sha256": hashlib.sha256(payload["lexicon.json"]).hexdigest(),
                    "records": 1,
                }
            ],
        }
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("manifest.json", json.dumps(manifest, separators=(",", ":")))
            archive.writestr("lexicon.json", payload["lexicon.json"])
        return stream.getvalue()

    def _upload(self, package=None):
        package = package or self._package()
        upload = SimpleUploadedFile("reference.zip", package, content_type="application/zip")
        return self.client.post("/api/superadmin/reference-datasets/validate/", {"package": upload}, format="multipart")

    def test_non_superadmin_cannot_list_or_upload_reference_packages(self):
        self.client.force_authenticate(user=self.member)

        listing = self.client.get("/api/superadmin/reference-datasets/")
        upload = self._upload()

        self.assertIn(listing.status_code, {401, 403})
        self.assertIn(upload.status_code, {401, 403})
        self.assertEqual(ReferenceDataset.objects.count(), 0)

    def test_superadmin_upload_validates_and_materializes_without_free_url_fetch(self):
        self.client.force_authenticate(user=self.admin)

        response = self._upload()

        self.assertEqual(response.status_code, 200)
        dataset = ReferenceDataset.objects.get()
        self.assertEqual(dataset.state, ReferenceDataset.State.PREVIEW)
        self.assertEqual(dataset.source_adapter, "operator_upload")
        self.assertEqual(dataset.record_count, 1)
        self.assertEqual(dataset.records.count(), 1)
        self.assertTrue(dataset.validation_summary["runtime_eligible"])
        self.assertTrue(dataset.validation_summary["materialized"])
        self.assertEqual(response.data["dataset"]["dataset_id"], dataset.dataset_id)
        self.assertNotIn("package", response.data["dataset"])
        audit = AuditEvent.objects.get(event_key="superadmin.reference_data.validated")
        self.assertEqual(audit.actor_id, self.admin.id)
        self.assertEqual(audit.target_type, "reference_data")
        self.assertEqual(audit.target_id, str(dataset.id))
        self.assertEqual(audit.reason, "admin_action")

    def test_structurally_invalid_upload_returns_bounded_error_without_registry_row(self):
        self.client.force_authenticate(user=self.admin)
        upload = SimpleUploadedFile("reference.zip", b"not-a-zip", content_type="application/zip")

        response = self.client.post("/api/superadmin/reference-datasets/validate/", {"package": upload}, format="multipart")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["code"], "malformed_archive")
        self.assertEqual(ReferenceDataset.objects.count(), 0)

    def test_operator_activate_uses_revision_and_changes_only_valid_preview(self):
        self.client.force_authenticate(user=self.admin)
        upload = self._upload()
        dataset_id = upload.data["dataset"]["id"]
        revision = upload.data["dataset"]["state_revision"]

        with patch("family.shopping_reference_operator_views._sensitive_guard", return_value=None):
            response = self.client.post(
                f"/api/superadmin/reference-datasets/{dataset_id}/activate/",
                {"expected_revision": revision},
                format="json",
            )

        self.assertEqual(response.status_code, 200)
        dataset = ReferenceDataset.objects.get(pk=dataset_id)
        self.assertEqual(dataset.state, ReferenceDataset.State.ACTIVE)
        self.assertGreater(dataset.state_revision, revision)
        self.assertEqual(response.data["dataset"]["state"], "active")
        self.assertTrue(
            AuditEvent.objects.filter(
                event_key="superadmin.reference_data.activated",
                actor=self.admin,
                target_type="reference_data",
                target_id=str(dataset.id),
            ).exists()
        )

    def test_stale_operator_revision_is_rejected_without_second_transition(self):
        self.client.force_authenticate(user=self.admin)
        upload = self._upload()
        dataset_id = upload.data["dataset"]["id"]
        revision = upload.data["dataset"]["state_revision"]

        with patch("family.shopping_reference_operator_views._sensitive_guard", return_value=None):
            first = self.client.post(
                f"/api/superadmin/reference-datasets/{dataset_id}/activate/",
                {"expected_revision": revision},
                format="json",
            )
            stale = self.client.post(
                f"/api/superadmin/reference-datasets/{dataset_id}/disable/",
                {"expected_revision": revision},
                format="json",
            )

        self.assertEqual(first.status_code, 200)
        self.assertEqual(stale.status_code, 409)
        self.assertEqual(stale.data["code"], "revision_conflict")
        self.assertEqual(ReferenceDataset.objects.get(pk=dataset_id).state, ReferenceDataset.State.ACTIVE)

    def test_deferred_rights_preview_cannot_be_activated(self):
        self.client.force_authenticate(user=self.admin)
        upload = self._upload(self._package(dataset_id="shopping.de.lexicon.defer-operator", redistribution="defer"))
        dataset_id = upload.data["dataset"]["id"]
        revision = upload.data["dataset"]["state_revision"]

        with patch("family.shopping_reference_operator_views._sensitive_guard", return_value=None):
            response = self.client.post(
                f"/api/superadmin/reference-datasets/{dataset_id}/activate/",
                {"expected_revision": revision},
                format="json",
            )

        self.assertEqual(response.status_code, 409)
        self.assertIn(response.data["code"], {"rights_blocked", "runtime_blocked"})
        self.assertEqual(ReferenceDataset.objects.get(pk=dataset_id).state, ReferenceDataset.State.PREVIEW)

    def test_detail_exposes_bounded_technical_history_not_household_data(self):
        self.client.force_authenticate(user=self.admin)
        upload = self._upload()
        dataset_id = upload.data["dataset"]["id"]

        response = self.client.get(f"/api/superadmin/reference-datasets/{dataset_id}/")

        self.assertEqual(response.status_code, 200)
        self.assertIn("events", response.data)
        self.assertLessEqual(len(response.data["events"]), 30)
        self.assertNotIn("family", response.data["dataset"])
        self.assertNotIn("user", response.data["dataset"])
        self.assertNotIn("shopping_items", response.data["dataset"])
