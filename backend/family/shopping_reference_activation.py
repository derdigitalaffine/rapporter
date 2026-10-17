import re
import uuid
from datetime import timedelta

from django.db import IntegrityError, transaction
from django.utils import timezone

from .shopping_reference_models import (
    ReferenceDataset,
    ReferenceDatasetActivationEvent,
    ReferenceDatasetLease,
)
from .shopping_reference_registry import active_reference_datasets


DEFAULT_LEASE_SECONDS = 120
MAX_LEASE_SECONDS = 900
_DATASET_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{2,179}$")
_OWNER_RE = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
_REASON_CODE_RE = re.compile(r"^[a-z0-9._-]{0,80}$")


class ReferenceActivationError(ValueError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


class ReferenceDatasetLeaseBusy(ReferenceActivationError):
    pass


class ReferenceDatasetRevisionConflict(ReferenceActivationError):
    pass


class ReferenceDatasetActivationBlocked(ReferenceActivationError):
    pass


def _error(error_class, code, message):
    raise error_class(code, message)


def _technical_id(value, field):
    pattern = _DATASET_ID_RE if field == "dataset_id" else _OWNER_RE
    if not isinstance(value, str) or not pattern.fullmatch(value):
        _error(ReferenceActivationError, "invalid_technical_id", f"{field} must be a technical identifier")
    return value


def _reason_code(value):
    value = value or ""
    if not isinstance(value, str) or not _REASON_CODE_RE.fullmatch(value):
        _error(ReferenceActivationError, "invalid_reason_code", "reason_code must be a lowercase technical code")
    return value


def _ttl_seconds(value):
    if not isinstance(value, int) or isinstance(value, bool) or not 1 <= value <= MAX_LEASE_SECONDS:
        _error(
            ReferenceActivationError,
            "invalid_lease_ttl",
            f"lease ttl must be between 1 and {MAX_LEASE_SECONDS} seconds",
        )
    return value


def _token(value):
    try:
        return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))
    except (ValueError, TypeError, AttributeError) as exc:
        raise ReferenceActivationError("invalid_lease_token", "lease token must be a UUID") from exc


def acquire_reference_dataset_lease(dataset_id, *, owner, ttl_seconds=DEFAULT_LEASE_SECONDS):
    """Acquire or renew the short lease for one semantic dataset id."""
    dataset_id = _technical_id(dataset_id, "dataset_id")
    owner = _technical_id(owner, "owner")
    ttl_seconds = _ttl_seconds(ttl_seconds)
    now = timezone.now()
    expires_at = now + timedelta(seconds=ttl_seconds)

    try:
        with transaction.atomic():
            lease = ReferenceDatasetLease.objects.select_for_update().filter(dataset_id=dataset_id).first()
            if lease is None:
                return ReferenceDatasetLease.objects.create(
                    dataset_id=dataset_id,
                    owner=owner,
                    expires_at=expires_at,
                )
            if lease.expires_at > now:
                if lease.owner != owner:
                    _error(
                        ReferenceDatasetLeaseBusy,
                        "lease_busy",
                        f"dataset {dataset_id} is leased by another worker",
                    )
                lease.expires_at = expires_at
                lease.save(update_fields=["expires_at", "updated_at"])
                return lease
            lease.owner = owner
            lease.token = uuid.uuid4()
            lease.expires_at = expires_at
            lease.save(update_fields=["owner", "token", "expires_at", "updated_at"])
            return lease
    except IntegrityError as exc:
        raise ReferenceDatasetLeaseBusy(
            "lease_busy",
            f"dataset {dataset_id} lease was acquired concurrently",
        ) from exc


def renew_reference_dataset_lease(dataset_id, *, lease_token, ttl_seconds=DEFAULT_LEASE_SECONDS):
    dataset_id = _technical_id(dataset_id, "dataset_id")
    lease_token = _token(lease_token)
    ttl_seconds = _ttl_seconds(ttl_seconds)
    now = timezone.now()
    with transaction.atomic():
        lease = ReferenceDatasetLease.objects.select_for_update().filter(dataset_id=dataset_id).first()
        if lease is None or lease.token != lease_token or lease.expires_at <= now:
            _error(ReferenceDatasetLeaseBusy, "lease_lost", f"dataset {dataset_id} lease is no longer owned")
        lease.expires_at = now + timedelta(seconds=ttl_seconds)
        lease.save(update_fields=["expires_at", "updated_at"])
        return lease


def release_reference_dataset_lease(dataset_id, *, lease_token):
    dataset_id = _technical_id(dataset_id, "dataset_id")
    lease_token = _token(lease_token)
    with transaction.atomic():
        lease = ReferenceDatasetLease.objects.select_for_update().filter(dataset_id=dataset_id).first()
        if lease is None:
            return False
        if lease.token != lease_token:
            _error(ReferenceDatasetLeaseBusy, "lease_lost", f"dataset {dataset_id} lease is no longer owned")
        lease.delete()
        return True


def _lock_valid_lease(dataset_id, lease_token):
    lease_token = _token(lease_token)
    now = timezone.now()
    lease = ReferenceDatasetLease.objects.select_for_update().filter(dataset_id=dataset_id).first()
    if lease is None or lease.token != lease_token or lease.expires_at <= now:
        _error(ReferenceDatasetLeaseBusy, "lease_lost", f"dataset {dataset_id} requires a current lease")
    return lease


def _check_revision(dataset, expected_revision):
    if not isinstance(expected_revision, int) or isinstance(expected_revision, bool) or expected_revision < 0:
        _error(ReferenceActivationError, "invalid_revision", "expected_revision must be a non-negative integer")
    if dataset.state_revision != expected_revision:
        _error(
            ReferenceDatasetRevisionConflict,
            "revision_conflict",
            f"expected revision {expected_revision}, current revision is {dataset.state_revision}",
        )


def _check_dependencies_active(dataset):
    missing = []
    for dependency in dataset.dependencies or []:
        if not isinstance(dependency, dict):
            missing.append("invalid-dependency")
            continue
        dataset_id = dependency.get("dataset_id")
        version = dependency.get("version")
        if not dataset_id or not version:
            missing.append("invalid-dependency")
            continue
        if not active_reference_datasets().filter(dataset_id=dataset_id, version=version).exists():
            missing.append(f"{dataset_id}@{version}")
    if missing:
        _error(
            ReferenceDatasetActivationBlocked,
            "inactive_dependency",
            f"dependencies are not active: {', '.join(missing)}",
        )


def _check_runtime_candidate(dataset, *, allowed_states):
    if dataset.state not in allowed_states:
        _error(
            ReferenceDatasetActivationBlocked,
            "invalid_state",
            f"dataset state {dataset.state} cannot be activated",
        )
    if dataset.redistribution not in {
        ReferenceDataset.Redistribution.ADOPT,
        ReferenceDataset.Redistribution.ADAPT,
    }:
        _error(
            ReferenceDatasetActivationBlocked,
            "rights_blocked",
            f"redistribution policy {dataset.redistribution} is not runtime eligible",
        )
    if not dataset.validated_at or dataset.validation_summary.get("valid") is not True:
        _error(ReferenceDatasetActivationBlocked, "not_validated", "dataset has not passed package validation")
    if dataset.validation_summary.get("runtime_eligible") is not True:
        _error(ReferenceDatasetActivationBlocked, "runtime_blocked", "validation marked dataset runtime-ineligible")
    if dataset.validation_error:
        _error(ReferenceDatasetActivationBlocked, "validation_error", "dataset still has a validation error")
    _check_dependencies_active(dataset)


def _event(*, dataset_id, action, from_version="", to_version="", state_revision=0, reason_code=""):
    return ReferenceDatasetActivationEvent.objects.create(
        dataset_id=dataset_id,
        action=action,
        from_version=from_version,
        to_version=to_version,
        state_revision=state_revision,
        reason_code=_reason_code(reason_code),
    )


def activate_reference_dataset(dataset_pk, *, lease_token, expected_revision, reason_code="manual_activate"):
    """Atomically replace the active version for a semantic dataset id."""
    with transaction.atomic():
        candidate = ReferenceDataset.objects.select_for_update().get(pk=dataset_pk)
        _lock_valid_lease(candidate.dataset_id, lease_token)
        if candidate.state == ReferenceDataset.State.ACTIVE:
            return candidate
        _check_revision(candidate, expected_revision)
        _check_runtime_candidate(
            candidate,
            allowed_states={ReferenceDataset.State.PREVIEW, ReferenceDataset.State.DISABLED},
        )
        previous = (
            ReferenceDataset.objects.select_for_update()
            .filter(dataset_id=candidate.dataset_id, state=ReferenceDataset.State.ACTIVE)
            .exclude(pk=candidate.pk)
            .first()
        )

        candidate.state = ReferenceDataset.State.ACTIVATING
        candidate.state_revision += 1
        candidate.save(update_fields=["state", "state_revision", "updated_at"])

        if previous is not None:
            previous.state = ReferenceDataset.State.DISABLED
            previous.state_revision += 1
            previous.save(update_fields=["state", "state_revision", "updated_at"])

        candidate.state = ReferenceDataset.State.ACTIVE
        candidate.state_revision += 1
        candidate.activated_at = timezone.now()
        candidate.save(update_fields=["state", "state_revision", "activated_at", "updated_at"])
        _event(
            dataset_id=candidate.dataset_id,
            action=ReferenceDatasetActivationEvent.Action.ACTIVATE,
            from_version=previous.version if previous else "",
            to_version=candidate.version,
            state_revision=candidate.state_revision,
            reason_code=reason_code,
        )
        return candidate


def disable_reference_dataset(dataset_pk, *, lease_token, expected_revision, reason_code="manual_disable"):
    """Disable a package without deleting metadata, history, or household data."""
    with transaction.atomic():
        dataset = ReferenceDataset.objects.select_for_update().get(pk=dataset_pk)
        _lock_valid_lease(dataset.dataset_id, lease_token)
        if dataset.state == ReferenceDataset.State.DISABLED:
            return dataset
        _check_revision(dataset, expected_revision)
        if dataset.state in {ReferenceDataset.State.ACTIVATING, ReferenceDataset.State.ROLLBACK}:
            _error(ReferenceDatasetActivationBlocked, "transition_busy", "dataset is in a transitional state")
        previous_state = dataset.state
        dataset.state = ReferenceDataset.State.DISABLED
        dataset.state_revision += 1
        dataset.save(update_fields=["state", "state_revision", "updated_at"])
        _event(
            dataset_id=dataset.dataset_id,
            action=ReferenceDatasetActivationEvent.Action.DISABLE,
            from_version=dataset.version if previous_state == ReferenceDataset.State.ACTIVE else "",
            to_version="",
            state_revision=dataset.state_revision,
            reason_code=reason_code,
        )
        return dataset


def rollback_reference_dataset(dataset_id, *, lease_token, expected_revision, reason_code="manual_rollback"):
    """Atomically restore the version preceding the current activation transition."""
    dataset_id = _technical_id(dataset_id, "dataset_id")
    with transaction.atomic():
        _lock_valid_lease(dataset_id, lease_token)
        current = (
            ReferenceDataset.objects.select_for_update()
            .filter(dataset_id=dataset_id, state=ReferenceDataset.State.ACTIVE)
            .first()
        )
        if current is None:
            _error(ReferenceDatasetActivationBlocked, "no_active_version", f"dataset {dataset_id} has no active version")
        _check_revision(current, expected_revision)

        transition = (
            ReferenceDatasetActivationEvent.objects.filter(
                dataset_id=dataset_id,
                to_version=current.version,
                action__in=[
                    ReferenceDatasetActivationEvent.Action.ACTIVATE,
                    ReferenceDatasetActivationEvent.Action.ROLLBACK,
                ],
            )
            .exclude(from_version="")
            .order_by("-created_at", "-id")
            .first()
        )
        if transition is None:
            _error(ReferenceDatasetActivationBlocked, "no_rollback_target", "no previous version is recorded")
        target = (
            ReferenceDataset.objects.select_for_update()
            .filter(dataset_id=dataset_id, version=transition.from_version)
            .first()
        )
        if target is None:
            _error(ReferenceDatasetActivationBlocked, "rollback_target_missing", "previous package metadata is missing")
        _check_runtime_candidate(target, allowed_states={ReferenceDataset.State.DISABLED})

        current.state = ReferenceDataset.State.ROLLBACK
        current.state_revision += 1
        current.save(update_fields=["state", "state_revision", "updated_at"])
        current.state = ReferenceDataset.State.DISABLED
        current.state_revision += 1
        current.save(update_fields=["state", "state_revision", "updated_at"])

        target.state = ReferenceDataset.State.ACTIVATING
        target.state_revision += 1
        target.save(update_fields=["state", "state_revision", "updated_at"])
        target.state = ReferenceDataset.State.ACTIVE
        target.state_revision += 1
        target.activated_at = timezone.now()
        target.save(update_fields=["state", "state_revision", "activated_at", "updated_at"])

        _event(
            dataset_id=dataset_id,
            action=ReferenceDatasetActivationEvent.Action.ROLLBACK,
            from_version=current.version,
            to_version=target.version,
            state_revision=target.state_revision,
            reason_code=reason_code,
        )
        return target
