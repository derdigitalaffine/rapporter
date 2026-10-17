from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .shopping_reference_read import ReferenceReadError, lookup_reference_records, search_reference_records
from .shopping_reference_registry import active_reference_datasets


MAX_ACTIVE_DATASETS = 32


def _dataset_summary(dataset):
    return {
        "dataset_id": dataset.dataset_id,
        "version": dataset.version,
        "dataset_type": dataset.dataset_type,
        "locale": dataset.locale,
        "country": dataset.country,
        "region": dataset.region,
        "licence": dataset.licence,
        "attribution": dataset.attribution,
        "state_revision": dataset.state_revision,
        "record_count": dataset.record_count,
    }


def _read_error(exc):
    return Response({"code": exc.code, "detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def shopping_reference_active(request):
    datasets = list(
        active_reference_datasets()
        .filter(validation_summary__runtime_eligible=True)
        .order_by("dataset_id")[: MAX_ACTIVE_DATASETS + 1]
    )
    truncated = len(datasets) > MAX_ACTIVE_DATASETS
    datasets = datasets[:MAX_ACTIVE_DATASETS]
    return Response({"datasets": [_dataset_summary(dataset) for dataset in datasets], "truncated": truncated})


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def shopping_reference_search(request):
    exact_raw = request.query_params.get("exact", "0")
    if exact_raw not in {"0", "1"}:
        return Response(
            {"code": "invalid_exact", "detail": "exact must be 0 or 1"},
            status=status.HTTP_400_BAD_REQUEST,
        )
    try:
        payload = search_reference_records(
            dataset_type=request.query_params.get("type", "").strip(),
            query=request.query_params.get("q", ""),
            dataset_id=request.query_params.get("dataset_id"),
            locale=request.query_params.get("locale"),
            country=request.query_params.get("country"),
            limit=request.query_params.get("limit"),
            offset=request.query_params.get("offset"),
            exact=exact_raw == "1",
        )
    except ReferenceReadError as exc:
        return _read_error(exc)
    return Response(payload)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def shopping_reference_lookup(request):
    try:
        payload = lookup_reference_records(
            dataset_type=request.query_params.get("type", "").strip(),
            key=request.query_params.get("key", ""),
            dataset_id=request.query_params.get("dataset_id"),
            locale=request.query_params.get("locale"),
            country=request.query_params.get("country"),
            limit=request.query_params.get("limit", 10),
        )
    except ReferenceReadError as exc:
        return _read_error(exc)
    return Response(payload)
