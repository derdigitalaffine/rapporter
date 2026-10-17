from django.db import IntegrityError, models, transaction
from django.test import TestCase

from .shopping_reference_models import ReferenceDataset
from .shopping_reference_registry import active_reference_datasets, reference_dataset_versions


class ShoppingReferenceRegistryTests(TestCase):
    def _dataset(self, **overrides):
        values = {
            "dataset_id": "shopping.de.food-lexicon.sample",
            "dataset_type": ReferenceDataset.DatasetType.LEXICON,
            "schema_version": 1,
            "version": "2026-10-16.1",
            "source_url": "https://example.test/reference-package",
            "source_revision": "abc123",
            "locale": "de-DE",
            "country": "DE",
            "licence": "repository terms",
            "attribution": "Project-authored sample",
            "redistribution": ReferenceDataset.Redistribution.ADOPT,
            "checksum": "a" * 64,
            "coverage": {"completeness_claim": False},
            "quality": {"ambiguous_input_policy": "ABSTAIN"},
            "dependencies": [],
            "manifest": {
                "data_kind": "food_lexicon_and_eval",
                "privacy": {"contains_private_family_corrections": False},
            },
        }
        values.update(overrides)
        return ReferenceDataset.objects.create(**values)

    def test_zero_packages_is_valid_default(self):
        self.assertEqual(reference_dataset_versions().count(), 0)
        self.assertEqual(active_reference_datasets().count(), 0)

    def test_registry_supports_all_public_dataset_types_and_states(self):
        dataset_types = [choice for choice, _label in ReferenceDataset.DatasetType.choices]
        states = [choice for choice, _label in ReferenceDataset.State.choices]

        self.assertEqual(
            set(dataset_types),
            {"store_reference", "lexicon", "gtin_product", "store_layout_evidence"},
        )
        self.assertEqual(
            set(states),
            {"staged", "validating", "preview", "activating", "active", "failed", "stale", "disabled", "rollback"},
        )

    def test_dataset_id_and_version_are_idempotent_registry_key(self):
        self._dataset()
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                self._dataset()

        newer = self._dataset(version="2026-10-17.1", checksum="b" * 64)
        self.assertEqual(newer.dataset_id, "shopping.de.food-lexicon.sample")
        self.assertEqual(reference_dataset_versions(dataset_id=newer.dataset_id).count(), 2)

    def test_active_registry_filters_state_and_type(self):
        self._dataset(state=ReferenceDataset.State.STAGED)
        active_lexicon = self._dataset(
            dataset_id="shopping.de.food-lexicon.active",
            version="1",
            checksum="b" * 64,
            state=ReferenceDataset.State.ACTIVE,
        )
        self._dataset(
            dataset_id="shopping.de.store-reference.active",
            dataset_type=ReferenceDataset.DatasetType.STORE_REFERENCE,
            version="1",
            checksum="c" * 64,
            state=ReferenceDataset.State.ACTIVE,
        )

        self.assertEqual(active_reference_datasets().count(), 2)
        self.assertEqual(
            list(active_reference_datasets(dataset_type=ReferenceDataset.DatasetType.LEXICON)),
            [active_lexicon],
        )

    def test_research_manifest_semantics_are_preserved_without_becoming_domain_truth(self):
        dataset = self._dataset(redistribution=ReferenceDataset.Redistribution.DEFER)

        self.assertEqual(dataset.quality["ambiguous_input_policy"], "ABSTAIN")
        self.assertFalse(dataset.coverage["completeness_claim"])
        self.assertEqual(dataset.redistribution, "defer")
        self.assertEqual(dataset.manifest["data_kind"], "food_lexicon_and_eval")

    def test_public_reference_registry_has_no_household_or_user_relationships(self):
        forbidden_fields = {
            "family",
            "family_id",
            "user",
            "user_id",
            "created_by",
            "shopping_list",
            "shopping_item",
            "item_name",
        }
        field_names = {field.name for field in ReferenceDataset._meta.get_fields()}

        self.assertTrue(forbidden_fields.isdisjoint(field_names))
        self.assertFalse(
            any(
                isinstance(field, (models.ForeignKey, models.OneToOneField, models.ManyToManyField))
                for field in ReferenceDataset._meta.get_fields()
            )
        )
