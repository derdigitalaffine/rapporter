import hashlib
import io
import json
import zipfile

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from .shopping_reference_models import (
    ReferenceDataset,
    ReferenceDatasetRecord,
    ReferenceDatasetSearchTerm,
)
from .shopping_reference_records import (
    ReferenceRecordMaterializationError,
    materialize_reference_dataset,
    normalize_reference_term,
)
from .shopping_reference_validation import (
    ReferencePackageVersionConflict,
    reference_content_checksum,
    stage_reference_package,
)


class ShoppingReferenceReadApiTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="reference-reader", password="x")
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def _dataset(self, *, dataset_id="shopping.de.lexicon.read-test", dataset_type="lexicon", version="1", state="active", redistribution="adopt", quality=None, attribution="Fixture authors"):
        return ReferenceDataset.objects.create(
            dataset_id=dataset_id,
            dataset_type=dataset_type,
            schema_version=1,
            version=version,
            licence="CC0-1.0",
            attribution=attribution,
            redistribution=redistribution,
            checksum="sha256:" + hashlib.sha256(f"{dataset_id}:{version}".encode()).hexdigest(),
            quality=quality if quality is not None else ({"ambiguous_input_policy": "ABSTAIN"} if dataset_type == "lexicon" else {}),
            state=state,
            validated_at=timezone.now(),
            validation_summary={"valid": True, "runtime_eligible": redistribution in {"adopt", "adapt"}, "materialized": True},
        )

    def _lexicon_payload(self, entries):
        return {"lexicon.json": json.dumps({"entries": entries}, ensure_ascii=False).encode("utf-8")}

    def _package(self, *, attribution="Fixture authors"):
        payload = self._lexicon_payload(
            [
                {"id": "food.oat", "label_de": "Hafermilch", "aliases": ["Haferdrink"]},
                {"id": "food.bread", "label_de": "Brot", "aliases": ["Vollkornbrot"]},
            ]
        )
        content = payload["lexicon.json"]
        manifest = {
            "schema_version": 1,
            "dataset_id": "shopping.de.lexicon.retry-test",
            "dataset_type": "lexicon",
            "version": "2026-10-17.1",
            "source_url": "https://example.test/reference/lexicon",
            "source_revision": "fixture-1",
            "locale": "de-DE",
            "country": "DE",
            "licence": "CC0-1.0",
            "attribution": attribution,
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
            "files": [
                {
                    "path": "lexicon.json",
                    "sha256": hashlib.sha256(content).hexdigest(),
                    "records": 2,
                }
            ],
        }
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("manifest.json", json.dumps(manifest, separators=(",", ":"), ensure_ascii=False))
            archive.writestr("lexicon.json", content)
        return stream.getvalue()

    def test_lexicon_materializes_primary_alias_and_id_terms(self):
        dataset = self._dataset(state=ReferenceDataset.State.PREVIEW)
        result = materialize_reference_dataset(
            dataset,
            self._lexicon_payload(
                [{"id": "food.oat", "label_de": "Hafermilch", "aliases": ["Haferdrink", "  HAFER DRINK  "]}]
            ),
        )

        self.assertEqual(result["records"], 1)
        self.assertEqual(result["tombstones"], 0)
        record = ReferenceDatasetRecord.objects.get(dataset=dataset)
        self.assertEqual(record.record_key, "id:food.oat")
        self.assertEqual(record.lookup_key, "hafermilch")
        terms = set(ReferenceDatasetSearchTerm.objects.filter(record=record).values_list("term", flat=True))
        self.assertEqual(terms, {"food.oat", "hafermilch", "haferdrink", "hafer drink"})

    def test_lexicon_materialization_requires_abstain_policy(self):
        dataset = self._dataset(state=ReferenceDataset.State.PREVIEW, quality={})
        with self.assertRaises(ReferenceRecordMaterializationError) as caught:
            materialize_reference_dataset(dataset, self._lexicon_payload([{"id": "food.milk", "label_de": "Milch"}]))
        self.assertEqual(caught.exception.code, "lexicon_policy")
        self.assertEqual(ReferenceDatasetRecord.objects.filter(dataset=dataset).count(), 0)

    def test_gtin_materialization_enforces_length_and_check_digit(self):
        dataset = self._dataset(
            dataset_id="shopping.de.gtin.read-test",
            dataset_type=ReferenceDataset.DatasetType.GTIN_PRODUCT,
            state=ReferenceDataset.State.PREVIEW,
        )
        result = materialize_reference_dataset(
            dataset,
            {"products.json": json.dumps({"products": [{"gtin": "4006381333931", "name": "Example"}]}).encode()},
        )
        self.assertEqual(result["records"], 1)
        self.assertTrue(ReferenceDatasetSearchTerm.objects.filter(dataset=dataset, term="4006381333931").exists())

        with self.assertRaises(ReferenceRecordMaterializationError) as caught:
            materialize_reference_dataset(
                dataset,
                {"products.json": json.dumps({"products": [{"gtin": "4006381333932", "name": "Broken"}]}).encode()},
            )
        self.assertEqual(caught.exception.code, "invalid_gtin")

    def test_duplicate_record_keys_fail_before_replacing_existing_materialization(self):
        dataset = self._dataset(state=ReferenceDataset.State.PREVIEW)
        materialize_reference_dataset(dataset, self._lexicon_payload([{"id": "food.safe", "label_de": "Safe"}]))
        with self.assertRaises(ReferenceRecordMaterializationError) as caught:
            materialize_reference_dataset(
                dataset,
                self._lexicon_payload(
                    [
                        {"id": "food.duplicate", "label_de": "One"},
                        {"id": "food.duplicate", "label_de": "Two"},
                    ]
                ),
            )
        self.assertEqual(caught.exception.code, "duplicate_record_key")
        self.assertTrue(ReferenceDatasetRecord.objects.filter(dataset=dataset, record_key="id:food.safe").exists())

    def test_tombstones_are_materialized_without_search_terms(self):
        dataset = self._dataset(state=ReferenceDataset.State.PREVIEW)
        result = materialize_reference_dataset(
            dataset,
            self._lexicon_payload([{"id": "food.old", "label_de": "Alt", "tombstone": True}]),
        )
        record = ReferenceDatasetRecord.objects.get(dataset=dataset)
        self.assertTrue(record.tombstone)
        self.assertEqual(result["tombstones"], 1)
        self.assertEqual(ReferenceDatasetSearchTerm.objects.filter(record=record).count(), 0)

    def test_active_package_retry_keeps_active_state_and_materialized_records(self):
        package = self._package()
        dataset = stage_reference_package(package, source_adapter="repository_fixture")
        self.assertEqual(dataset.state, ReferenceDataset.State.PREVIEW)
        self.assertTrue(dataset.validation_summary["materialized"])
        dataset.state = ReferenceDataset.State.ACTIVE
        dataset.state_revision = 7
        dataset.save(update_fields=["state", "state_revision", "updated_at"])
        record_ids = list(dataset.records.order_by("id").values_list("id", flat=True))

        retried = stage_reference_package(package, source_adapter="operator_upload")

        self.assertEqual(retried.id, dataset.id)
        self.assertEqual(retried.state, ReferenceDataset.State.ACTIVE)
        self.assertEqual(retried.state_revision, 7)
        self.assertEqual(list(retried.records.order_by("id").values_list("id", flat=True)), record_ids)

    def test_changed_manifest_is_version_conflict_even_with_same_payload_checksum(self):
        stage_reference_package(self._package(attribution="Original attribution"), source_adapter="repository_fixture")
        with self.assertRaises(ReferencePackageVersionConflict) as caught:
            stage_reference_package(self._package(attribution="Changed attribution"), source_adapter="repository_fixture")
        self.assertEqual(caught.exception.code, "version_conflict")

    def test_active_endpoint_is_authenticated_and_returns_only_runtime_safe_packages(self):
        active = self._dataset(attribution="Public attribution")
        active.record_count = 3
        active.save(update_fields=["record_count", "updated_at"])
        self._dataset(
            dataset_id="shopping.de.lexicon.preview",
            state=ReferenceDataset.State.PREVIEW,
            version="1",
        )
        self._dataset(
            dataset_id="shopping.de.lexicon.deferred",
            redistribution=ReferenceDataset.Redistribution.DEFER,
            state=ReferenceDataset.State.ACTIVE,
            version="1",
        )

        response = self.client.get("/api/shopping-reference/active/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data["datasets"]), 1)
        self.assertEqual(response.data["datasets"][0]["dataset_id"], active.dataset_id)
        self.assertEqual(response.data["datasets"][0]["attribution"], "Public attribution")
        self.assertNotIn("manifest", response.data["datasets"][0])
        self.assertNotIn("source_url", response.data["datasets"][0])

        anonymous = APIClient().get("/api/shopping-reference/active/")
        self.assertIn(anonymous.status_code, {401, 403})

    def test_prefix_alias_search_reads_only_active_non_tombstone_records(self):
        active = self._dataset()
        materialize_reference_dataset(
            active,
            self._lexicon_payload(
                [
                    {"id": "food.oat", "label_de": "Hafermilch", "aliases": ["Haferdrink"]},
                    {"id": "food.old", "label_de": "Hafer alt", "tombstone": True},
                ]
            ),
        )
        preview = self._dataset(
            dataset_id="shopping.de.lexicon.preview-only",
            state=ReferenceDataset.State.PREVIEW,
        )
        materialize_reference_dataset(
            preview,
            self._lexicon_payload([{"id": "food.preview", "label_de": "Hafer Preview"}]),
        )

        response = self.client.get("/api/shopping-reference/search/?type=lexicon&q=hafer")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data["results"]), 1)
        self.assertEqual(response.data["results"][0]["record_key"], "id:food.oat")
        self.assertEqual(response.data["results"][0]["payload"]["label_de"], "Hafermilch")
        self.assertNotIn("family", response.data["results"][0])

    def test_exact_gtin_search(self):
        dataset = self._dataset(
            dataset_id="shopping.de.gtin.active",
            dataset_type=ReferenceDataset.DatasetType.GTIN_PRODUCT,
        )
        materialize_reference_dataset(
            dataset,
            {"products.json": json.dumps({"products": [{"gtin": "4006381333931", "name": "Example"}]}).encode()},
        )

        response = self.client.get(
            "/api/shopping-reference/search/?type=gtin_product&q=4006381333931&exact=1"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data["results"]), 1)
        self.assertEqual(response.data["results"][0]["payload"]["gtin"], "4006381333931")

    def test_search_limit_is_bounded_and_reports_truncation(self):
        dataset = self._dataset()
        entries = [
            {"id": f"food.milk.{index:03d}", "label_de": f"Milch {index:03d}"}
            for index in range(55)
        ]
        materialize_reference_dataset(dataset, self._lexicon_payload(entries))

        response = self.client.get("/api/shopping-reference/search/?type=lexicon&q=milch&limit=50")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data["results"]), 50)
        self.assertTrue(response.data["truncated"])

    def test_search_rejects_invalid_type_query_exact_country_and_limit(self):
        cases = [
            "/api/shopping-reference/search/?type=unknown&q=milk",
            "/api/shopping-reference/search/?type=lexicon&q=x",
            "/api/shopping-reference/search/?type=lexicon&q=milk&limit=51",
            "/api/shopping-reference/search/?type=lexicon&q=milk&limit=nope",
            "/api/shopping-reference/search/?type=lexicon&q=milk&exact=yes",
            "/api/shopping-reference/search/?type=lexicon&q=milk&country=de",
        ]
        for url in cases:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 400)

    def test_zero_packages_returns_empty_bounded_results(self):
        ReferenceDataset.objects.all().delete()
        active = self.client.get("/api/shopping-reference/active/")
        search = self.client.get("/api/shopping-reference/search/?type=lexicon&q=milk")
        self.assertEqual(active.status_code, 200)
        self.assertEqual(active.data["datasets"], [])
        self.assertEqual(search.status_code, 200)
        self.assertEqual(search.data["results"], [])

    def test_term_normalization_is_unicode_casefolded_and_whitespace_bounded(self):
        self.assertEqual(normalize_reference_term("  HAFER\u00a0MILCH  "), "hafer milch")
        self.assertLessEqual(len(normalize_reference_term("x" * 500)), 200)
