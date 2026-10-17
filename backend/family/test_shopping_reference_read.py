from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import models
from django.test import TestCase
from rest_framework.test import APIClient

from .shopping_reference_models import (
    ReferenceDataset,
    ReferenceDatasetRecord,
    ReferenceDatasetSearchTerm,
)
from .shopping_reference_read import ReferenceReadError, lookup_reference_records, search_reference_records
from .shopping_reference_records import ReferenceRecordMaterializationError, materialize_reference_dataset


class ShoppingReferenceReadTests(TestCase):
    def _dataset(self, *, dataset_id="shopping.de.lexicon.test", dataset_type=ReferenceDataset.DatasetType.LEXICON, state=ReferenceDataset.State.ACTIVE, redistribution=ReferenceDataset.Redistribution.ADOPT, locale="de-DE", country="DE", quality=None):
        return ReferenceDataset.objects.create(
            dataset_id=dataset_id,
            dataset_type=dataset_type,
            schema_version=1,
            version="1",
            source_adapter="repository_fixture",
            locale=locale,
            country=country,
            licence="CC0-1.0",
            attribution="Fixture authors",
            redistribution=redistribution,
            checksum="sha256:" + "a" * 64,
            quality=quality if quality is not None else ({"ambiguous_input_policy": "ABSTAIN"} if dataset_type == ReferenceDataset.DatasetType.LEXICON else {}),
            manifest={"files": []},
            validation_summary={"valid": True, "runtime_eligible": redistribution in {"adopt", "adapt"}, "materialized": True},
            state=state,
        )

    def _record(self, dataset, *, key, name, tombstone=False, aliases=None):
        record = ReferenceDatasetRecord.objects.create(
            dataset=dataset,
            record_key=key,
            source_path="fixture.json",
            ordinal=dataset.records.count() + 1,
            payload={"id": key, "label_de": name, **({"aliases": aliases} if aliases else {})},
            lookup_key=name.casefold(),
            tombstone=tombstone,
        )
        if not tombstone:
            ReferenceDatasetSearchTerm.objects.create(dataset=dataset, record=record, term=name.casefold(), kind="primary")
        return record

    def test_materializer_indexes_csv_aliases_and_drops_unknown_private_fields(self):
        dataset = self._dataset(dataset_id="shopping.de.store.test", dataset_type=ReferenceDataset.DatasetType.STORE_REFERENCE, quality={})
        payload = {
            "chains.csv": (
                "chain_id,canonical_name,aliases,user_id,private_note\n"
                "de.rewe,REWE,Rewe|REWE City,123,should-never-be-public\n"
            ).encode()
        }

        result = materialize_reference_dataset(dataset, payload)
        record = dataset.records.get()
        terms = set(record.search_terms.values_list("term", flat=True))

        self.assertEqual(result["records"], 1)
        self.assertEqual(record.payload["chain_id"], "de.rewe")
        self.assertEqual(record.payload["canonical_name"], "REWE")
        self.assertNotIn("user_id", record.payload)
        self.assertNotIn("private_note", record.payload)
        self.assertIn("rewe", terms)
        self.assertIn("rewe city", terms)

    def test_store_samples_use_branch_identity_before_shared_chain_id(self):
        dataset = self._dataset(dataset_id="shopping.de.store.branches", dataset_type=ReferenceDataset.DatasetType.STORE_REFERENCE, quality={})
        payload = {
            "sampling.csv": (
                "chain_id,sample_id,canonical_name,public_place_hint\n"
                "de.rewe,rewe-mitte,REWE,Mitte\n"
                "de.rewe,rewe-west,REWE,West\n"
            ).encode()
        }

        result = materialize_reference_dataset(dataset, payload)
        keys = set(dataset.records.values_list("record_key", flat=True))

        self.assertEqual(result["records"], 2)
        self.assertEqual(keys, {"sample_id:rewe-mitte", "sample_id:rewe-west"})

    def test_global_search_term_budget_fails_before_replacing_existing_index(self):
        dataset = self._dataset()
        existing = self._record(dataset, key="existing", name="Bestehend")
        payload = {"lexicon.json": b'{"entries":[{"id":"food.milk","label_de":"Milch"}]}' }

        with patch("family.shopping_reference_records.MAX_TOTAL_SEARCH_TERMS", 1):
            with self.assertRaises(ReferenceRecordMaterializationError) as caught:
                materialize_reference_dataset(dataset, payload)

        self.assertEqual(caught.exception.code, "too_many_search_terms")
        self.assertTrue(ReferenceDatasetRecord.objects.filter(pk=existing.pk).exists())

    def test_materializer_rejects_lexicon_without_abstain_contract(self):
        dataset = self._dataset(quality={})
        payload = {"lexicon.json": b'{"entries":[{"id":"food.milk","label_de":"Milch"}]}' }

        with self.assertRaises(ReferenceRecordMaterializationError) as caught:
            materialize_reference_dataset(dataset, payload)

        self.assertEqual(caught.exception.code, "lexicon_policy")
        self.assertEqual(dataset.records.count(), 0)

    def test_materializer_rejects_invalid_gtin(self):
        dataset = self._dataset(dataset_id="shopping.de.gtin.test", dataset_type=ReferenceDataset.DatasetType.GTIN_PRODUCT, quality={})
        payload = {"products.csv": b"gtin,product_name\n3017620422004,Nutella\n"}

        with self.assertRaises(ReferenceRecordMaterializationError) as caught:
            materialize_reference_dataset(dataset, payload)

        self.assertEqual(caught.exception.code, "invalid_gtin")
        self.assertEqual(dataset.records.count(), 0)

    def test_search_reads_only_active_runtime_eligible_non_tombstone_records(self):
        active = self._dataset()
        preview = self._dataset(dataset_id="shopping.de.lexicon.preview", state=ReferenceDataset.State.PREVIEW)
        deferred = self._dataset(dataset_id="shopping.de.lexicon.defer", redistribution=ReferenceDataset.Redistribution.DEFER)
        self._record(active, key="food.milk", name="Milch")
        self._record(active, key="food.milk.deleted", name="Milch alt", tombstone=True)
        self._record(preview, key="food.milk.preview", name="Milch preview")
        self._record(deferred, key="food.milk.defer", name="Milch defer")

        result = search_reference_records(dataset_type="lexicon", query="mil", limit=20)

        self.assertEqual([row["record_key"] for row in result["results"]], ["food.milk"])
        self.assertEqual(result["next_offset"], None)

    def test_search_is_bounded_paginated_and_exact_matches_rank_first(self):
        dataset = self._dataset()
        names = ["Milch", "Milch frisch", "Milch haltbar", "Milchpulver"]
        for index, name in enumerate(names):
            self._record(dataset, key=f"food.milk.{index}", name=name)

        first = search_reference_records(dataset_type="lexicon", query="milch", limit=2, offset=0)
        second = search_reference_records(dataset_type="lexicon", query="milch", limit=2, offset=2)

        self.assertEqual(first["results"][0]["payload"]["label_de"], "Milch")
        self.assertEqual(len(first["results"]), 2)
        self.assertEqual(first["next_offset"], 2)
        self.assertEqual(len(second["results"]), 2)
        self.assertIsNone(second["next_offset"])

    def test_lookup_and_scope_filters_are_deterministic(self):
        de = self._dataset(dataset_id="shopping.de.lexicon.de", locale="de-DE", country="DE")
        at = self._dataset(dataset_id="shopping.at.lexicon.at", locale="de-AT", country="AT")
        self._record(de, key="food.milk.de", name="Milch")
        self._record(at, key="food.milk.at", name="Milch")

        result = search_reference_records(dataset_type="lexicon", query="milch", country="DE", locale="de-DE")
        lookup = lookup_reference_records(dataset_type="lexicon", key="milch", dataset_id=de.dataset_id)

        self.assertEqual([row["record_key"] for row in result["results"]], ["food.milk.de"])
        self.assertEqual([row["record_key"] for row in lookup["results"]], ["food.milk.de"])

    def test_read_budgets_reject_unbounded_requests(self):
        with self.assertRaises(ReferenceReadError) as limit_error:
            search_reference_records(dataset_type="lexicon", query="milch", limit=51)
        with self.assertRaises(ReferenceReadError) as offset_error:
            search_reference_records(dataset_type="lexicon", query="milch", offset=1001)
        with self.assertRaises(ReferenceReadError) as query_error:
            search_reference_records(dataset_type="lexicon", query="x")

        self.assertEqual(limit_error.exception.code, "invalid_limit")
        self.assertEqual(offset_error.exception.code, "invalid_offset")
        self.assertEqual(query_error.exception.code, "invalid_query")

    def test_runtime_record_models_have_no_household_or_user_relationships(self):
        forbidden = {"family", "family_id", "user", "user_id", "shopping_list", "shopping_item", "item_name"}
        for model in (ReferenceDatasetRecord, ReferenceDatasetSearchTerm):
            fields = {field.name for field in model._meta.get_fields()}
            self.assertTrue(forbidden.isdisjoint(fields))
            relations = [
                field
                for field in model._meta.get_fields()
                if isinstance(field, (models.ForeignKey, models.OneToOneField, models.ManyToManyField))
            ]
            self.assertTrue(all(field.related_model in {ReferenceDataset, ReferenceDatasetRecord} for field in relations))

    def test_reference_api_requires_authentication_and_returns_bounded_results(self):
        dataset = self._dataset()
        self._record(dataset, key="food.milk", name="Milch")
        client = APIClient()

        anonymous = client.get("/api/shopping-reference/search/", {"type": "lexicon", "q": "milch"})
        self.assertIn(anonymous.status_code, {401, 403})

        user = get_user_model().objects.create_user(username="reference-reader", password="not-used")
        client.force_authenticate(user=user)
        response = client.get("/api/shopping-reference/search/", {"type": "lexicon", "q": "milch", "limit": 1})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["limit"], 1)
        self.assertEqual(response.data["results"][0]["record_key"], "food.milk")
        self.assertEqual(response.data["results"][0]["source"]["dataset_id"], dataset.dataset_id)
