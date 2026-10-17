from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.decorators import api_view, parser_classes, permission_classes
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response

from telemetry.service import try_record_audit_event

from .shopping_reference_activation import (
    ReferenceActivationError,
    ReferenceDatasetActivationBlocked,
    ReferenceDatasetLeaseBusy,
    ReferenceDatasetRevisionConflict,
    acquire_reference_dataset_lease,
    activate_reference_dataset,
    disable_reference_dataset,
    release_reference_dataset_lease,
    rollback_reference_dataset,
)
from .shopping_reference_models import ReferenceDataset, ReferenceDatasetActivationEvent
from .shopping_reference_validation import MAX_PACKAGE_BYTES, ReferencePackageError, ReferencePackageVersionConflict, stage_reference_package
from .superadmin_views import IsSuperAdmin, _enforce_sensitive_action, _rate_limited_response


MAX_OPERATOR_DATASETS = 100
MAX_OPERATOR_EVENTS = 30
_ALLOWED_STATES = {value for value, _label in ReferenceDataset.State.choices}
_ALLOWED_TYPES = {value for value, _label in ReferenceDataset.DatasetType.choices}
_ALLOWED_ACTIONS = {"activate", "disable", "rollback"}


def _error(detail, code, http_status=status.HTTP_400_BAD_REQUEST, **extra):
    return Response({"detail": detail, "code": code, **extra}, status=http_status)


def _serialize(dataset, *, include_manifest=False):
    summary = dataset.validation_summary or {}
    payload = {
        "id": str(dataset.id),
        "dataset_id": dataset.dataset_id,
        "dataset_type": dataset.dataset_type,
        "schema_version": dataset.schema_version,
        "version": dataset.version,
        "source_adapter": dataset.source_adapter,
        "source_url": dataset.source_url,
        "source_revision": dataset.source_revision,
        "locale": dataset.locale,
        "country": dataset.country,
        "region": dataset.region,
        "licence": dataset.licence,
        "attribution": dataset.attribution,
        "redistribution": dataset.redistribution,
        "checksum": dataset.checksum,
        "coverage": dataset.coverage,
        "quality": dataset.quality,
        "dependencies": dataset.dependencies,
        "state": dataset.state,
        "state_revision": dataset.state_revision,
        "package_size_bytes": dataset.package_size_bytes,
        "record_count": dataset.record_count,
        "runtime_eligible": summary.get("runtime_eligible") is True,
        "validation": summary,
        "validation_error": dataset.validation_error,
        "installed_at": dataset.installed_at,
        "validated_at": dataset.validated_at,
        "activated_at": dataset.activated_at,
        "updated_at": dataset.updated_at,
    }
    if include_manifest:
        payload["manifest"] = dataset.manifest
    return payload


def _event_row(event):
    return {
        "id": str(event.id),
        "action": event.action,
        "from_version": event.from_version,
        "to_version": event.to_version,
        "state_revision": event.state_revision,
        "reason_code": event.reason_code,
        "created_at": event.created_at,
    }


def _queryset(request):
    queryset = ReferenceDataset.objects.all()
    dataset_type = str(request.query_params.get("type") or "").strip()
    state_value = str(request.query_params.get("state") or "").strip()
    dataset_id = str(request.query_params.get("dataset_id") or "").strip()
    if dataset_type:
        if dataset_type not in _ALLOWED_TYPES:
            return None, _error("Unbekannter Datensatztyp.", "invalid_dataset_type", allowed=sorted(_ALLOWED_TYPES))
        queryset = queryset.filter(dataset_type=dataset_type)
    if state_value:
        if state_value not in _ALLOWED_STATES:
            return None, _error("Unbekannter Paketstatus.", "invalid_state", allowed=sorted(_ALLOWED_STATES))
        queryset = queryset.filter(state=state_value)
    if dataset_id:
        queryset = queryset.filter(dataset_id=dataset_id)
    return queryset.order_by("dataset_id", "-created_at"), None


def _sensitive_guard(request):
    decision = _enforce_sensitive_action(request)
    if not decision.allowed:
        return _rate_limited_response(decision)
    return None


def _audit(event_key, request, dataset):
    try_record_audit_event(
        event_key,
        actor=request.user,
        actor_class="superadmin",
        reason="admin_action",
        target_type="reference_data",
        target_id=str(dataset.id),
    )


def _activation_error(exc):
    if isinstance(exc, ReferenceDatasetLeaseBusy):
        http_status = status.HTTP_409_CONFLICT
    elif isinstance(exc, ReferenceDatasetRevisionConflict):
        http_status = status.HTTP_409_CONFLICT
    elif isinstance(exc, ReferenceDatasetActivationBlocked):
        http_status = status.HTTP_409_CONFLICT
    else:
        http_status = status.HTTP_400_BAD_REQUEST
    return _error(str(exc), exc.code, http_status=http_status)


def _expected_revision(request):
    value = request.data.get("expected_revision")
    if isinstance(value, bool):
        raise ValueError("expected_revision must be an integer")
    try:
        value = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("expected_revision must be an integer") from exc
    if value < 0:
        raise ValueError("expected_revision must be non-negative")
    return value


def _transition_state_error(dataset, action):
    if action not in _ALLOWED_ACTIONS:
        return _error("Unbekannte Paketaktion.", "invalid_action", http_status=status.HTTP_404_NOT_FOUND)
    if action == "activate" and dataset.state not in {
        ReferenceDataset.State.PREVIEW,
        ReferenceDataset.State.DISABLED,
        ReferenceDataset.State.ACTIVE,
    }:
        return _error("Paket ist in diesem Status nicht aktivierbar.", "invalid_state", http_status=status.HTTP_409_CONFLICT)
    if action in {"disable", "rollback"} and dataset.state != ReferenceDataset.State.ACTIVE:
        return _error("Nur die aktive Paketversion kann diese Aktion ausführen.", "invalid_state", http_status=status.HTTP_409_CONFLICT)
    return None


def _run_transition(request, dataset, action):
    lifecycle_error = _transition_state_error(dataset, action)
    if lifecycle_error:
        return lifecycle_error
    guard = _sensitive_guard(request)
    if guard:
        return guard
    try:
        expected_revision = _expected_revision(request)
    except ValueError as exc:
        return _error(str(exc), "invalid_revision")

    owner = f"superadmin:{request.user.pk}"
    try:
        lease = acquire_reference_dataset_lease(dataset.dataset_id, owner=owner)
    except ReferenceActivationError as exc:
        return _activation_error(exc)
    try:
        if action == "activate":
            updated = activate_reference_dataset(
                dataset.pk,
                lease_token=lease.token,
                expected_revision=expected_revision,
                reason_code="operator_activate",
            )
            audit_key = "superadmin.reference_data.activated"
        elif action == "disable":
            updated = disable_reference_dataset(
                dataset.pk,
                lease_token=lease.token,
                expected_revision=expected_revision,
                reason_code="operator_disable",
            )
            audit_key = "superadmin.reference_data.disabled"
        else:
            updated = rollback_reference_dataset(
                dataset.dataset_id,
                lease_token=lease.token,
                expected_revision=expected_revision,
                reason_code="operator_rollback",
            )
            audit_key = "superadmin.reference_data.rolled_back"
    except ReferenceActivationError as exc:
        return _activation_error(exc)
    finally:
        try:
            release_reference_dataset_lease(dataset.dataset_id, lease_token=lease.token)
        except ReferenceActivationError:
            pass

    _audit(audit_key, request, updated)
    return Response({"dataset": _serialize(updated, include_manifest=True)})


@api_view(["GET"])
@permission_classes([IsSuperAdmin])
def superadmin_reference_datasets(request):
    queryset, error = _queryset(request)
    if error:
        return error
    rows = list(queryset[: MAX_OPERATOR_DATASETS + 1])
    truncated = len(rows) > MAX_OPERATOR_DATASETS
    rows = rows[:MAX_OPERATOR_DATASETS]
    return Response({"results": [_serialize(row) for row in rows], "truncated": truncated, "limit": MAX_OPERATOR_DATASETS})


@api_view(["GET"])
@permission_classes([IsSuperAdmin])
def superadmin_reference_dataset_detail(request, dataset_pk):
    dataset = get_object_or_404(ReferenceDataset, pk=dataset_pk)
    active = (
        ReferenceDataset.objects.filter(dataset_id=dataset.dataset_id, state=ReferenceDataset.State.ACTIVE)
        .exclude(pk=dataset.pk)
        .first()
    )
    events = ReferenceDatasetActivationEvent.objects.filter(dataset_id=dataset.dataset_id)[:MAX_OPERATOR_EVENTS]
    return Response(
        {
            "dataset": _serialize(dataset, include_manifest=True),
            "active_other_version": _serialize(active) if active else None,
            "events": [_event_row(event) for event in events],
        }
    )


@api_view(["POST"])
@permission_classes([IsSuperAdmin])
@parser_classes([MultiPartParser, FormParser])
def superadmin_reference_dataset_validate(request):
    package = request.FILES.get("package")
    if package is None:
        return _error("ZIP-Paket fehlt.", "package_required")
    if package.size <= 0 or package.size > MAX_PACKAGE_BYTES:
        return _error(
            f"ZIP-Paket muss zwischen 1 und {MAX_PACKAGE_BYTES} Bytes groß sein.",
            "package_size",
            http_status=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
        )
    try:
        package_bytes = package.read(MAX_PACKAGE_BYTES + 1)
    except OSError:
        return _error("ZIP-Paket konnte nicht gelesen werden.", "package_read_error")
    if len(package_bytes) > MAX_PACKAGE_BYTES:
        return _error("ZIP-Paket überschreitet das Größenlimit.", "package_size", http_status=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE)
    try:
        dataset = stage_reference_package(package_bytes, source_adapter="operator_upload")
    except ReferencePackageVersionConflict as exc:
        return _error(str(exc), exc.code, http_status=status.HTTP_409_CONFLICT)
    except ReferencePackageError as exc:
        return _error(str(exc), exc.code)

    _audit("superadmin.reference_data.validated", request, dataset)
    http_status = status.HTTP_200_OK if dataset.validation_summary.get("valid") else status.HTTP_422_UNPROCESSABLE_ENTITY
    return Response({"dataset": _serialize(dataset, include_manifest=True)}, status=http_status)


@api_view(["POST"])
@permission_classes([IsSuperAdmin])
@parser_classes([JSONParser])
def superadmin_reference_dataset_action(request, dataset_pk, action):
    dataset = get_object_or_404(ReferenceDataset, pk=dataset_pk)
    return _run_transition(request, dataset, action)
