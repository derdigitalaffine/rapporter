from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .shopping_reference_models import ReferenceDataset, ReferenceDatasetRecord, ReferenceDatasetSearchTerm
from .shopping_reference_records import normalize_reference_term
from .shopping_reference_registry import active_reference_datasets


MAX_ACTIVE_DATASETS = 32
DEFAULT_SEARCH_LIMIT = 12
MAX_SEARCH_LIMIT = 50


def _bad_request(detail):
    return Response({"detail": detail}, status=status.HTTP_400_BAD_REQUEST)


def _dataset_summary(dataset):
    return {
        "dataset_id": dataset.dataset_id,
        "version": dataset.version,
        "dataset_type": dataset.dataset_type,
        "locale": dataset.locale,
        "country": dataset.country,
        "region": dataset.region,
        "attribution": dataset.attribution,
        "state_revision": dataset.state_revision,
        "record_count": dataset.record_count,
    }


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def shopping_reference_active(request):
    datasets = list(active_reference_datasets().order_by("dataset_id")[: MAX_ACTIVE_DATASETS + 1])
    truncated = len(datasets) > MAX_ACTIVE_DATASETS
    datasets = datasets[:MAX_ACTIVE_DATASETS]
    return Response(
        {
            "datasets": [_dataset_summary(dataset) for dataset in datasets],
            "truncated": truncated,
        }
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def shopping_reference_search(request):
    dataset_type = request.query_params.get("type", "").strip()
    allowed_types = {value for value, _label in ReferenceDataset.DatasetType.choices}
    if dataset_type not in allowed_types:
        return _bad_request("type must be a supported reference dataset type")

    raw_query = request.query_params.get("q", "")
    if not isinstance(raw_query, str) or len(raw_query) > 200:
        return _bad_request("q must contain at most 200 characters")
    query = normalize_reference_term(raw_query)
    if len(query) < 2:
        return _bad_request("q must contain at least 2 normalized characters")

    raw_limit = request.query_params.get("limit", str(DEFAULT_SEARCH_LIMIT))
    try:
        limit = int(raw_limit)
    except (TypeError, ValueError):
        return _bad_request("limit must be an integer")
    if not 1 <= limit <= MAX_SEARCH_LIMIT:
        return _bad_request(f"limit must be between 1 and {MAX_SEARCH_LIMIT}")

    exact_raw = request.query_params.get("exact", "0")
    if exact_raw not in {"0", "1"}:
        return _bad_request("exact must be 0 or 1")
    exact = exact_raw == "1"

    locale = request.query_params.get("locale", "").strip()
    country = request.query_params.get("country", "").strip()
    if len(locale) > 32:
        return _bad_request("locale must contain at most 32 characters")
    if country and (len(country) != 2 or not country.isalpha() or country.upper() != country):
        return _bad_request("country must be an uppercase two-letter code")

    datasets = active_reference_datasets(dataset_type=dataset_type)
    if locale:
        datasets = datasets.filter(locale=locale)
    if country:
        datasets = datasets.filter(country=country)

    terms = ReferenceDatasetSearchTerm.objects.filter(
        dataset__in=datasets,
        record__tombstone=False,
    )
    if exact:
        terms = terms.filter(term=query)
    else:
        terms = terms.filter(term__startswith=query)

    record_ids = list(
        terms.order_by("record_id")
        .values_list("record_id", flat=True)
        .distinct()[: limit + 1]
    )
    truncated = len(record_ids) > limit
    record_ids = record_ids[:limit]
    records = list(
        ReferenceDatasetRecord.objects.filter(id__in=record_ids, tombstone=False)
        .select_related("dataset")
        .order_by("dataset__dataset_id", "record_key", "id")
    )

    return Response(
        {
            "results": [
                {
                    "dataset_id": record.dataset.dataset_id,
                    "version": record.dataset.version,
                    "dataset_type": record.dataset.dataset_type,
                    "record_key": record.record_key,
                    "payload": record.payload,
                    "attribution": record.dataset.attribution,
                }
                for record in records
            ],
            "limit": limit,
            "truncated": truncated,
        }
    )
