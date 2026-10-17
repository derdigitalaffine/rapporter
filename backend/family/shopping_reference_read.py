import re

from django.db.models import Exists, OuterRef

from .shopping_reference_models import ReferenceDataset, ReferenceDatasetRecord, ReferenceDatasetSearchTerm
from .shopping_reference_records import normalize_reference_term
from .shopping_reference_registry import active_reference_datasets


DEFAULT_QUERY_LIMIT = 20
MAX_QUERY_LIMIT = 50
MAX_QUERY_OFFSET = 1000
MAX_QUERY_LENGTH = 120
_DATASET_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{2,179}$")


class ReferenceReadError(ValueError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def _dataset_type(value):
    allowed = {choice for choice, _label in ReferenceDataset.DatasetType.choices}
    if value not in allowed:
        raise ReferenceReadError("invalid_dataset_type", "dataset_type is required and must be canonical")
    return value


def _dataset_id(value):
    if value in (None, ""):
        return None
    value = str(value).strip()
    if not _DATASET_ID_RE.fullmatch(value):
        raise ReferenceReadError("invalid_dataset_id", "dataset_id must be a canonical technical identifier")
    return value


def _limit(value):
    try:
        value = DEFAULT_QUERY_LIMIT if value in (None, "") else int(value)
    except (TypeError, ValueError) as exc:
        raise ReferenceReadError("invalid_limit", "limit must be an integer") from exc
    if value < 1 or value > MAX_QUERY_LIMIT:
        raise ReferenceReadError("invalid_limit", f"limit must be between 1 and {MAX_QUERY_LIMIT}")
    return value


def _offset(value):
    try:
        value = 0 if value in (None, "") else int(value)
    except (TypeError, ValueError) as exc:
        raise ReferenceReadError("invalid_offset", "offset must be an integer") from exc
    if value < 0 or value > MAX_QUERY_OFFSET:
        raise ReferenceReadError("invalid_offset", f"offset must be between 0 and {MAX_QUERY_OFFSET}")
    return value


def _active_records(dataset_type, dataset_id=None, *, locale=None, country=None):
    datasets = active_reference_datasets(dataset_type=dataset_type).filter(validation_summary__runtime_eligible=True)
    if dataset_id:
        datasets = datasets.filter(dataset_id=dataset_id)
    if locale:
        datasets = datasets.filter(locale=locale)
    if country:
        datasets = datasets.filter(country=country)
    return ReferenceDatasetRecord.objects.filter(dataset__in=datasets, tombstone=False).select_related("dataset")


def serialize_reference_record(record):
    dataset = record.dataset
    return {
        "record_key": record.record_key,
        "lookup_key": record.lookup_key,
        "payload": record.payload,
        "source": {
            "dataset_id": dataset.dataset_id,
            "version": dataset.version,
            "dataset_type": dataset.dataset_type,
            "locale": dataset.locale,
            "country": dataset.country,
            "region": dataset.region,
            "licence": dataset.licence,
            "attribution": dataset.attribution,
            "state_revision": dataset.state_revision,
        },
    }


def search_reference_records(
    *,
    dataset_type,
    query,
    dataset_id=None,
    locale=None,
    country=None,
    limit=None,
    offset=None,
    exact=False,
):
    dataset_type = _dataset_type(dataset_type)
    dataset_id = _dataset_id(dataset_id)
    limit = _limit(limit)
    offset = _offset(offset)
    query = normalize_reference_term(query)
    if len(query) < 2 or len(query) > MAX_QUERY_LENGTH:
        raise ReferenceReadError("invalid_query", f"query length must be between 2 and {MAX_QUERY_LENGTH}")
    if locale is not None and len(str(locale)) > 32:
        raise ReferenceReadError("invalid_locale", "locale must contain at most 32 characters")
    locale = str(locale or "").strip() or None
    country = str(country or "").strip() or None
    if country and (len(country) != 2 or not country.isalpha() or country.upper() != country):
        raise ReferenceReadError("invalid_country", "country must be an uppercase two-letter code")

    records = _active_records(dataset_type, dataset_id, locale=locale, country=country)
    exact_term = ReferenceDatasetSearchTerm.objects.filter(record_id=OuterRef("pk"), term=query)
    if exact:
        records = records.filter(search_terms__term=query)
    else:
        records = records.filter(search_terms__term__startswith=query)
    records = (
        records.annotate(exact_match=Exists(exact_term))
        .distinct()
        .order_by("-exact_match", "lookup_key", "record_key", "id")
    )
    rows = list(records[offset : offset + limit + 1])
    has_more = len(rows) > limit
    rows = rows[:limit]
    next_offset = offset + limit if has_more and offset + limit <= MAX_QUERY_OFFSET else None
    return {
        "results": [serialize_reference_record(row) for row in rows],
        "limit": limit,
        "offset": offset,
        "next_offset": next_offset,
        "truncated": has_more,
    }


def lookup_reference_records(*, dataset_type, key, dataset_id=None, locale=None, country=None, limit=10):
    dataset_type = _dataset_type(dataset_type)
    dataset_id = _dataset_id(dataset_id)
    limit = min(_limit(limit), 10)
    key = normalize_reference_term(key)
    if not key or len(key) > 255:
        raise ReferenceReadError("invalid_key", "lookup key is required and must fit the runtime key budget")
    locale = str(locale or "").strip() or None
    country = str(country or "").strip() or None
    if locale and len(locale) > 32:
        raise ReferenceReadError("invalid_locale", "locale must contain at most 32 characters")
    if country and (len(country) != 2 or not country.isalpha() or country.upper() != country):
        raise ReferenceReadError("invalid_country", "country must be an uppercase two-letter code")

    rows = list(
        _active_records(dataset_type, dataset_id, locale=locale, country=country)
        .filter(lookup_key=key)
        .order_by("record_key", "id")[:limit]
    )
    return {"results": [serialize_reference_record(row) for row in rows], "limit": limit}
