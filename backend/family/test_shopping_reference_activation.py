from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from .models import Family, Membership, ShoppingItem, ShoppingList
from .shopping_reference_activation import (
    ReferenceActivationError,
    ReferenceDatasetActivationBlocked,
    ReferenceDatasetLeaseBusy,
    ReferenceDatasetRevisionConflict,
    acquire_reference_dataset_lease,
    activate_reference_dataset,
    disable_reference_dataset,
    release_reference_dataset_lease,
    renew_reference_dataset_lease,
    rollback_reference_dataset,
)
from .shopping_reference_models import (
    ReferenceDataset,
    ReferenceDatasetActivationEvent,
    ReferenceDatasetLease,
)
from .shopping_reference_registry import active_reference_datasets


class ShoppingReferenceActivationTests(TestCase):
    dataset_id = "shopping.de.lexicon.activation-test"

    def _dataset(self, version, **overrides):
        values = {
            "dataset_id": self.dataset_id,
            "dataset_type": ReferenceDataset.DatasetType.LEXICON,
            "schema_version": 1,
            "version": version,
            "licence": "CC0-1.0",
            "attribution": "Fixture authors",
            "redistribution": ReferenceDataset.Redistribution.ADOPT,
            "checksum": "sha256:" + (version[-1] if version[-1].isalnum() else "a") * 64,
            "state": ReferenceDataset.State.PREVIEW,
            "validated_at": timezone.now(),
            "validation_summary": {
                "valid": True,
                "runtime_eligible": True,
                "blockers": [],
            },
        }
        values.update(overrides)
        return ReferenceDataset.objects.create(**values)

    def _lease(self, owner="worker-a"):
        return acquire_reference_dataset_lease(self.dataset_id, owner=owner)

    def test_lease_is_exclusive_renewable_and_expired_lease_can_be_taken_over(self):
        first = self._lease("worker-a")
        renewed = acquire_reference_dataset_lease(self.dataset_id, owner="worker-a")
        self.assertEqual(first.token, renewed.token)

        with self.assertRaises(ReferenceDatasetLeaseBusy) as caught:
            self._lease("worker-b")
        self.assertEqual(caught.exception.code, "lease_busy")

        ReferenceDatasetLease.objects.filter(dataset_id=self.dataset_id).update(
            expires_at=timezone.now() - timedelta(seconds=1)
        )
        takeover = self._lease("worker-b")
        self.assertNotEqual(first.token, takeover.token)
        self.assertEqual(takeover.owner, "worker-b")

        with self.assertRaises(ReferenceDatasetLeaseBusy):
            renew_reference_dataset_lease(self.dataset_id, lease_token=first.token)
        renewed_takeover = renew_reference_dataset_lease(self.dataset_id, lease_token=takeover.token)
        self.assertGreater(renewed_takeover.expires_at, timezone.now())
        self.assertTrue(release_reference_dataset_lease(self.dataset_id, lease_token=takeover.token))
        self.assertFalse(release_reference_dataset_lease(self.dataset_id, lease_token=takeover.token))

    def test_activation_is_atomic_single_active_and_retry_idempotent(self):
        first = self._dataset("1")
        lease = self._lease()

        active = activate_reference_dataset(first.id, lease_token=lease.token, expected_revision=0)
        self.assertEqual(active.state, ReferenceDataset.State.ACTIVE)
        self.assertEqual(active.state_revision, 2)
        self.assertEqual(ReferenceDatasetActivationEvent.objects.count(), 1)

        retried = activate_reference_dataset(first.id, lease_token=lease.token, expected_revision=0)
        self.assertEqual(retried.id, first.id)
        self.assertEqual(ReferenceDatasetActivationEvent.objects.count(), 1)

        second = self._dataset("2", checksum="sha256:" + "b" * 64)
        second_active = activate_reference_dataset(second.id, lease_token=lease.token, expected_revision=0)
        first.refresh_from_db()
        self.assertEqual(first.state, ReferenceDataset.State.DISABLED)
        self.assertEqual(second_active.state, ReferenceDataset.State.ACTIVE)
        self.assertEqual(list(active_reference_datasets()), [second_active])
        latest = ReferenceDatasetActivationEvent.objects.first()
        self.assertEqual(latest.action, ReferenceDatasetActivationEvent.Action.ACTIVATE)
        self.assertEqual(latest.from_version, "1")
        self.assertEqual(latest.to_version, "2")

    def test_database_constraint_prevents_two_active_versions_even_outside_service(self):
        self._dataset("1", state=ReferenceDataset.State.ACTIVE)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                self._dataset("2", state=ReferenceDataset.State.ACTIVE, checksum="sha256:" + "b" * 64)

    def test_revision_conflict_changes_nothing(self):
        candidate = self._dataset("1")
        lease = self._lease()

        with self.assertRaises(ReferenceDatasetRevisionConflict) as caught:
            activate_reference_dataset(candidate.id, lease_token=lease.token, expected_revision=9)

        self.assertEqual(caught.exception.code, "revision_conflict")
        candidate.refresh_from_db()
        self.assertEqual(candidate.state, ReferenceDataset.State.PREVIEW)
        self.assertEqual(candidate.state_revision, 0)
        self.assertEqual(ReferenceDatasetActivationEvent.objects.count(), 0)

    def test_activation_rechecks_rights_validation_and_active_dependencies(self):
        deferred = self._dataset(
            "1",
            redistribution=ReferenceDataset.Redistribution.DEFER,
            validation_summary={"valid": True, "runtime_eligible": False, "blockers": ["redistribution_defer"]},
        )
        lease = self._lease()
        with self.assertRaises(ReferenceDatasetActivationBlocked) as caught:
            activate_reference_dataset(deferred.id, lease_token=lease.token, expected_revision=0)
        self.assertEqual(caught.exception.code, "rights_blocked")

        deferred.delete()
        dependency = ReferenceDataset.objects.create(
            dataset_id="shopping.de.dependency",
            dataset_type=ReferenceDataset.DatasetType.STORE_REFERENCE,
            schema_version=1,
            version="1",
            licence="CC0-1.0",
            redistribution=ReferenceDataset.Redistribution.ADOPT,
            checksum="sha256:" + "c" * 64,
            state=ReferenceDataset.State.PREVIEW,
            validated_at=timezone.now(),
            validation_summary={"valid": True, "runtime_eligible": True, "blockers": []},
        )
        candidate = self._dataset(
            "2",
            checksum="sha256:" + "d" * 64,
            dependencies=[{"dataset_id": dependency.dataset_id, "version": dependency.version}],
        )
        with self.assertRaises(ReferenceDatasetActivationBlocked) as caught:
            activate_reference_dataset(candidate.id, lease_token=lease.token, expected_revision=0)
        self.assertEqual(caught.exception.code, "inactive_dependency")
        candidate.refresh_from_db()
        self.assertEqual(candidate.state, ReferenceDataset.State.PREVIEW)

    def test_rollback_restores_previous_version_and_keeps_history(self):
        first = self._dataset("1")
        second = self._dataset("2", checksum="sha256:" + "b" * 64)
        lease = self._lease()
        first = activate_reference_dataset(first.id, lease_token=lease.token, expected_revision=0)
        second = activate_reference_dataset(second.id, lease_token=lease.token, expected_revision=0)

        restored = rollback_reference_dataset(
            self.dataset_id,
            lease_token=lease.token,
            expected_revision=second.state_revision,
        )

        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual(restored.id, first.id)
        self.assertEqual(first.state, ReferenceDataset.State.ACTIVE)
        self.assertEqual(second.state, ReferenceDataset.State.DISABLED)
        self.assertEqual(ReferenceDatasetActivationEvent.objects.count(), 3)
        event = ReferenceDatasetActivationEvent.objects.first()
        self.assertEqual(event.action, ReferenceDatasetActivationEvent.Action.ROLLBACK)
        self.assertEqual(event.from_version, "2")
        self.assertEqual(event.to_version, "1")

    def test_disable_never_deletes_private_shopping_data_or_reference_history(self):
        User = get_user_model()
        user = User.objects.create_user(username="reference-disable-owner", password="x")
        family = Family.objects.create(name="Private household", slug="reference-disable-family")
        Membership.objects.create(family=family, user=user, role=Membership.Role.OWNER)
        shopping_list = ShoppingList.objects.create(family=family, name="Private groceries")
        item = ShoppingItem.objects.create(shopping_list=shopping_list, name="Private milk", added_by=user)

        dataset = self._dataset("1")
        lease = self._lease()
        dataset = activate_reference_dataset(dataset.id, lease_token=lease.token, expected_revision=0)
        disabled = disable_reference_dataset(
            dataset.id,
            lease_token=lease.token,
            expected_revision=dataset.state_revision,
            reason_code="operator_disable",
        )

        self.assertEqual(disabled.state, ReferenceDataset.State.DISABLED)
        self.assertTrue(ShoppingItem.objects.filter(id=item.id, name="Private milk").exists())
        self.assertTrue(ReferenceDataset.objects.filter(id=dataset.id).exists())
        self.assertEqual(ReferenceDatasetActivationEvent.objects.count(), 2)

    def test_free_text_reason_is_rejected_and_transaction_rolls_back(self):
        candidate = self._dataset("1")
        lease = self._lease()

        with self.assertRaises(ReferenceActivationError) as caught:
            activate_reference_dataset(
                candidate.id,
                lease_token=lease.token,
                expected_revision=0,
                reason_code="Family Smith asked for this",
            )

        self.assertEqual(caught.exception.code, "invalid_reason_code")
        candidate.refresh_from_db()
        self.assertEqual(candidate.state, ReferenceDataset.State.PREVIEW)
        self.assertEqual(candidate.state_revision, 0)
        self.assertEqual(ReferenceDatasetActivationEvent.objects.count(), 0)
