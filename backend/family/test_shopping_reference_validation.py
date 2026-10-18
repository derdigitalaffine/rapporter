import hashlib
import io
import json
import zipfile

from django.test import TestCase

from .shopping_reference_models import ReferenceDataset
from .shopping_reference_registry import active_reference_datasets
from .shopping_reference_validation import (
    ReferencePackageError,
    ReferencePackageVersionConflict,
    reference_content_checksum,
    stage_reference_package,
)


class ShoppingReferenceValidationTests(TestCase):
    def _package(self, *, payload=None, manifest_overrides=None, file_overrides=None):
        payload = payload or {"lexicon.json": json.dumps({"entries": [{"id": "food.milk"}, {"id": "food.bread"}]}).encode()}
        specs = []
        for path, content in sorted(payload.items()):
            records = 2 if path == "lexicon.json" else 1
            specs.append(
                {
                    "path": path,
                    "sha256": hashlib.sha256(content).hexdigest(),
                    "records": records,
                }
            )
        if file_overrides:
            for index, values in file_overrides.items():
                specs[index].update(values)
        manifest = {
            "schema_version": 1,
            "dataset_id": "shopping.de.food-lexicon.runtime-test",
            "dataset_type": "lexicon",
            "version": "2026-10-17.1",
            "source_url": "https://example.test/reference/lexicon",
            "source_revision": "fixture-1",
            "locale": "de-DE",
            "country": "DE",
            "licence": "CC0-1.0",
            "attribution": "Fixture authors",
            "redistribution": "adopt",
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
            "files": specs,
        }
        if manifest_overrides:
            manifest.update(manifest_overrides)

        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("manifest.json", json.dumps(manifest, separators=(",", ":")))
            for path, content in payload.items():
                archive.writestr(path, content)
        return stream.getvalue()

    def test_valid_package_reaches_preview_with_deterministic_counts(self):
        package = self._package()

        dataset = stage_reference_package(package, source_adapter="repository_fixture")

        self.assertEqual(dataset.state, ReferenceDataset.State.PREVIEW)
        self.assertEqual(dataset.record_count, 2)
        self.assertTrue(dataset.validation_summary["valid"])
        self.assertTrue(dataset.validation_summary["runtime_eligible"])
        self.assertEqual(dataset.validation_summary["records"], 2)
        self.assertEqual(dataset.validation_summary["files"], {"lexicon.json": 2})
        self.assertEqual(dataset.package_size_bytes, len(package))
        self.assertEqual(dataset.source_adapter, "repository_fixture")
        self.assertIsNotNone(dataset.validated_at)

    def test_retry_of_same_version_and_checksum_is_idempotent(self):
        package = self._package()
        first = stage_reference_package(package, source_adapter="repository_fixture")
        second = stage_reference_package(package, source_adapter="repository_fixture")

        self.assertEqual(first.id, second.id)
        self.assertEqual(ReferenceDataset.objects.count(), 1)

    def test_same_version_with_different_content_is_immutable(self):
        first_package = self._package()
        stage_reference_package(first_package, source_adapter="repository_fixture")
        second_payload = {"lexicon.json": json.dumps({"entries": [{"id": "food.changed"}]}).encode()}
        second_package = self._package(payload=second_payload, file_overrides={0: {"records": 1}})

        with self.assertRaises(ReferencePackageVersionConflict) as caught:
            stage_reference_package(second_package, source_adapter="repository_fixture")

        self.assertEqual(caught.exception.code, "version_conflict")
        self.assertEqual(ReferenceDataset.objects.count(), 1)

    def test_unknown_adapter_is_rejected_before_package_processing(self):
        with self.assertRaises(ReferencePackageError) as caught:
            stage_reference_package(b"not even a zip", source_adapter="https://attacker.invalid/feed")

        self.assertEqual(caught.exception.code, "unknown_source_adapter")
        self.assertEqual(ReferenceDataset.objects.count(), 0)

    def test_path_traversal_is_rejected_without_registry_row(self):
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("manifest.json", "{}")
            archive.writestr("../escape.csv", "name\nsecret\n")

        with self.assertRaises(ReferencePackageError) as caught:
            stage_reference_package(stream.getvalue(), source_adapter="operator_upload")

        self.assertEqual(caught.exception.code, "unsafe_archive_path")
        self.assertEqual(ReferenceDataset.objects.count(), 0)

    def test_high_compression_ratio_is_rejected_before_decompression(self):
        payload = {"huge.txt": b"0" * (1024 * 1024)}
        package = self._package(payload=payload, file_overrides={0: {"records": 1}})

        with self.assertRaises(ReferencePackageError) as caught:
            stage_reference_package(package, source_adapter="operator_upload")

        self.assertEqual(caught.exception.code, "compression_ratio")
        self.assertEqual(ReferenceDataset.objects.count(), 0)

    def test_unexpected_executable_or_html_format_is_rejected(self):
        payload = {"payload.html": b"<script>alert(1)</script>"}
        package = self._package(payload=payload, file_overrides={0: {"records": 1}})

        with self.assertRaises(ReferencePackageError) as caught:
            stage_reference_package(package, source_adapter="operator_upload")

        self.assertEqual(caught.exception.code, "unsupported_format")
        self.assertEqual(ReferenceDataset.objects.count(), 0)

    def test_file_checksum_failure_is_persisted_as_failed_preview_candidate(self):
        package = self._package(file_overrides={0: {"sha256": "0" * 64}})

        dataset = stage_reference_package(package, source_adapter="operator_upload")

        self.assertEqual(dataset.state, ReferenceDataset.State.FAILED)
        self.assertEqual(dataset.validation_summary["blockers"], ["checksum_mismatch"])
        self.assertIn("SHA-256 mismatch", dataset.validation_error)
        self.assertEqual(active_reference_datasets().count(), 0)

    def test_missing_dependency_blocks_preview_without_affecting_other_versions(self):
        older = ReferenceDataset.objects.create(
            dataset_id="shopping.de.food-lexicon.stable",
            dataset_type=ReferenceDataset.DatasetType.LEXICON,
            schema_version=1,
            version="1",
            licence="CC0-1.0",
            redistribution=ReferenceDataset.Redistribution.ADOPT,
            checksum="sha256:" + "1" * 64,
            state=ReferenceDataset.State.ACTIVE,
        )
        package = self._package(
            manifest_overrides={
                "dependencies": [{"dataset_id": "shopping.de.missing", "version": "9"}],
            }
        )

        candidate = stage_reference_package(package, source_adapter="repository_fixture")

        self.assertEqual(candidate.state, ReferenceDataset.State.FAILED)
        self.assertEqual(candidate.validation_summary["blockers"], ["missing_dependency"])
        self.assertEqual(list(active_reference_datasets()), [older])

    def test_deferred_rights_can_be_previewed_but_never_become_runtime_visible(self):
        package = self._package(
            manifest_overrides={
                "licence": "unknown pending provider review",
                "redistribution": "defer",
            }
        )

        dataset = stage_reference_package(package, source_adapter="repository_fixture")

        self.assertEqual(dataset.state, ReferenceDataset.State.PREVIEW)
        self.assertTrue(dataset.validation_summary["valid"])
        self.assertFalse(dataset.validation_summary["runtime_eligible"])
        self.assertEqual(dataset.validation_summary["blockers"], ["redistribution_defer"])
        dataset.state = ReferenceDataset.State.ACTIVE
        dataset.save(update_fields=["state", "updated_at"])
        self.assertEqual(active_reference_datasets().filter(id=dataset.id).count(), 0)

    def test_private_household_package_is_rejected_before_registry_insert(self):
        package = self._package(
            manifest_overrides={
                "privacy": {"contains_private_household_data": True},
            }
        )

        with self.assertRaises(ReferencePackageError) as caught:
            stage_reference_package(package, source_adapter="operator_upload")

        self.assertEqual(caught.exception.code, "private_data")
        self.assertEqual(ReferenceDataset.objects.count(), 0)

    def test_unsupported_schema_is_rejected_without_registry_row(self):
        package = self._package(manifest_overrides={"schema_version": 2})

        with self.assertRaises(ReferencePackageError) as caught:
            stage_reference_package(package, source_adapter="repository_fixture")

        self.assertEqual(caught.exception.code, "unsupported_schema")
        self.assertEqual(ReferenceDataset.objects.count(), 0)
