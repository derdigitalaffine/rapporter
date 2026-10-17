import csv
import hashlib
import io
import json
import re
import unicodedata
from pathlib import PurePosixPath

from django.db import transaction
from django.db.models import Exists, OuterRef, Q

from .shopping_reference_models import (
    ReferenceDataset,
    ReferenceDatasetRecord,
    ReferenceDatasetSearchTerm,
)


MAX_MATERIALIZED_RECORDS = 100_000
MAX_RECORD_JSON_BYTES = 32 * 1024
MAX_SEARCH_TERMS_PER_RECORD = 24
DEFAULT_QUERY_LIMIT = 20
MAX_QUERY_LIMIT = 50
MAX_QUERY_OFFSET = 1000
MAX_QUERY_LENGTH = 120

_DATASET_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{2,179}$")
_RUNTIME_REDISTRIBUTION = {
    ReferenceDataset.Redistribution.ADOPT,
    ReferenceDataset.Redistribution.ADAPT,
}
_NON_RUNTIME_FILE_ROLES = {"evaluation", "eval", "evidence", "documentation", "docs"}
_TOMBSTONE_STATUSES = {"deleted", "removed", "tombstone"}


_RECORD_CONTRACTS = {
    ReferenceDataset.DatasetType.STORE_REFERENCE: {
        "fields": {
            "id", "store_id", "chain_id", "sample_id", "canonical_name", "name", "aliases",
            "operator_scope", "country_region", "wikidata_id", "nsi_id", "location_provider",
            "location_ref", "branch_label", "address", "city", "postcode", "latitude", "longitude",
            "source_namespace", "source_id", "source_revision", "verified_at", "confidence", "status",
            "source_status", "public_place_hint",
        },
        "key_fields": ("store_id", "chain_id", "id", "sample_id"),
        "primary_fields": ("canonical_name", "name", "branch_label", "public_place_hint"),
        "alias_fields": ("aliases",),
        "code_fields": ("store_id", "chain_id", "wikidata_id", "nsi_id", "location_ref", "source_id"),
    },
    ReferenceDataset.DatasetType.LEXICON: {
        "fields": {
            "id", "label_de", "label", "name", "parent_id", "shopping_department", "aliases",
            "negative_terms", "ambiguity", "provenance", "status",
        },
        "key_fields": ("id",),
        "primary_fields": ("label_de", "label", "name"),
        "alias_fields": ("aliases",),
        "code_fields": ("id", "parent_id", "shopping_department"),
    },
    ReferenceDataset.DatasetType.GTIN_PRODUCT: {
        "fields": {
            "id", "gtin", "product_name", "name", "brand", "quantity", "source_category",
            "mapped_category_id", "source_namespace", "source_id", "source_revision", "countries_evidence",
            "verified_at", "confidence", "status",
        },
        "key_fields": ("gtin", "id"),
        "primary_fields": ("product_name", "name", "brand"),
        "alias_fields": (),
        "code_fields": ("gtin", "source_id", "mapped_category_id"),
    },
    ReferenceDataset.DatasetType.STORE_LAYOUT_EVIDENCE: {
        "fields": {
            "id", "evidence_id", "layout_id", "store_ref", "store_id", "chain_id", "section_id",
            "section", "aisle", "category_id", "category", "position", "source_namespace", "source_id",
            "source_revision", "valid_from", "valid_to", "verified_at", "confidence", "status", "evidence",
        },
        "key_fields": ("id", "evidence_id", "layout_id", "section_id"),
        "primary_fields": ("section", "aisle", "category"),
        "alias_fields": (),
        "code_fields": ("store_ref", "store_id", "chain_id", "section_id", "category_id", "source_id"),
    },
}


class ReferenceMaterializationError(ValueError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


class ReferenceReadError(ValueError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def normalize_reference_term(value):
    value = unicodedata.normalize("NFKC", str(value or ""))
    return " ".join(value.casefold().split())


def _gtin_valid(value):
    digits = str(value or "").strip()
    if len(digits) not in {8, 12, 13, 14} or not digits.isdigit():
        return False
    body = [int(char) for char in digits[:-1]]
    total = 0
    for index, digit in enumerate(reversed(body)):
        total += digit * (3 if index % 2 == 0 else 1)
    check = (10 - (total % 10)) % 10
    return check == int(digits[-1])


def _decode_text(path, content):
    try:
        return content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ReferenceMaterializationError("invalid_encoding", f"{path} must be UTF-8 text") from exc


def _iter_records(path, content):
    suffix = PurePosixPath(path).suffix.lower()
    text = _decode_text(path, content)
    if suffix == ".csv":
        reader = csv.DictReader(io.StringIO(text))
        fieldnames = reader.fieldnames or []
        if not fieldnames or any(not str(name or "").strip() for name in fieldnames) or len(set(fieldnames)) != len(fieldnames):
            raise ReferenceMaterializationError("invalid_record_schema", f"{path} requires unique non-empty CSV headers")
        for row in reader:
            yield dict(row)
        return
    if suffix == ".jsonl":
        for line_number, line in enumerate(text.splitlines(), start=1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ReferenceMaterializationError("invalid_data", f"Invalid JSONL at {path}:{line_number}") from exc
            if not isinstance(value, dict):
                raise ReferenceMaterializationError("invalid_record_schema", f"{path}:{line_number} must be a JSON object")
            yield value
        return
    if suffix == ".json":
        try:
            value = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ReferenceMaterializationError("invalid_data", f"Invalid JSON: {path}") from exc
        if isinstance(value, list):
            rows = value
        elif isinstance(value, dict):
            rows = None
            for key in ("entries", "items", "products", "records"):
                if isinstance(value.get(key), list):
                    rows = value[key]
                    break
            if rows is None:
                rows = [value]
        else:
            raise ReferenceMaterializationError("invalid_record_schema", f"{path} must contain objects or an object list")
        for index, row in enumerate(rows, start=1):
            if not isinstance(row, dict):
                raise ReferenceMaterializationError("invalid_record_schema", f"{path} record {index} must be an object")
            yield row
        return
    if suffix == ".txt":
        for line in text.splitlines():
            if line.strip():
                yield {"value": line.strip()}
        return
    raise ReferenceMaterializationError("unsupported_format", f"Unsupported runtime record file: {path}")


def _runtime_paths(dataset, payload_files):
    specs = {str(spec.get("path")): spec for spec in dataset.manifest.get("files", []) if isinstance(spec, dict)}
    for path in sorted(payload_files):
        spec = specs.get(path, {})
        role = str(spec.get("role") or "records").strip().lower()
        if spec.get("runtime") is False or role in _NON_RUNTIME_FILE_ROLES:
            continue
        yield path


def _safe_payload(dataset_type, row):
    contract = _RECORD_CONTRACTS[dataset_type]
    payload = {key: row[key] for key in contract["fields"] if key in row and row[key] not in (None, "")}
    if not payload:
        raise ReferenceMaterializationError("unsupported_record_shape", f"No supported {dataset_type} fields found")
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    if len(encoded) > MAX_RECORD_JSON_BYTES:
        raise ReferenceMaterializationError("record_too_large", f"Runtime record exceeds {MAX_RECORD_JSON_BYTES} bytes")
    return payload


def _technical_value(value):
    if isinstance(value, (str, int)) and not isinstance(value, bool):
        cleaned = str(value).strip()
        return cleaned if cleaned else ""
    return ""


def _record_key(dataset_type, payload, path, ordinal):
    contract = _RECORD_CONTRACTS[dataset_type]
    for field in contract["key_fields"]:
        value = _technical_value(payload.get(field))
        if value:
            if len(value) > 240:
                raise ReferenceMaterializationError("record_key_too_long", f"{field} exceeds runtime key budget")
            return value
    digest = hashlib.sha256(path.encode("utf-8")).hexdigest()[:16]
    return f"auto:{digest}:{ordinal}"


def _split_terms(value):
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        return re.split(r"[|;]", value)
    return [value]


def _terms_for(dataset_type, payload, record_key):
    contract = _RECORD_CONTRACTS[dataset_type]
    candidates = []
    for field in contract["primary_fields"]:
        candidates.extend((value, ReferenceDatasetSearchTerm.Kind.PRIMARY) for value in _split_terms(payload.get(field)))
    for field in contract["alias_fields"]:
        candidates.extend((value, ReferenceDatasetSearchTerm.Kind.ALIAS) for value in _split_terms(payload.get(field)))
    for field in contract["code_fields"]:
        candidates.extend((value, ReferenceDatasetSearchTerm.Kind.CODE) for value in _split_terms(payload.get(field)))
    candidates.append((record_key, ReferenceDatasetSearchTerm.Kind.ID))

    result = []
    seen = set()
    for value, kind in candidates:
        term = normalize_reference_term(value)
        if not term:
            continue
        term = term[:200]
        if term in seen:
            continue
        seen.add(term)
        result.append((term, kind))
        if len(result) >= MAX_SEARCH_TERMS_PER_RECORD:
            break
    return result


def _tombstone(payload):
    if payload.get("tombstone") is True or payload.get("deleted") is True:
        return True
    return normalize_reference_term(payload.get("status")) in _TOMBSTONE_STATUSES


def materialize_reference_dataset(dataset, payload_files):
    """Replace one validated package's runtime records transactionally.

    Only canonical, allow-listed public fields are persisted. Unknown payload
    fields are deliberately dropped instead of becoming an accidental public
    query surface.
    """
    if dataset.dataset_type not in _RECORD_CONTRACTS:
        raise ReferenceMaterializationError("unsupported_dataset_type", "Dataset type has no runtime record contract")
    if dataset.redistribution not in _RUNTIME_REDISTRIBUTION:
        with transaction.atomic():
            dataset.records.all().delete()
        return 0

    seen_keys = set()
    count = 0
    with transaction.atomic():
        dataset.records.all().delete()
        record_batch = []
        term_batch = []

        def flush():
            nonlocal record_batch, term_batch
            if not record_batch:
                return
            ReferenceDatasetRecord.objects.bulk_create(record_batch, batch_size=500)
            ReferenceDatasetSearchTerm.objects.bulk_create(term_batch, batch_size=1000)
            record_batch = []
            term_batch = []

        for path in _runtime_paths(dataset, payload_files):
            content = payload_files[path]
            for ordinal, raw in enumerate(_iter_records(path, content), start=1):
                count += 1
                if count > MAX_MATERIALIZED_RECORDS:
                    raise ReferenceMaterializationError(
                        "too_many_runtime_records",
                        f"Runtime package exceeds {MAX_MATERIALIZED_RECORDS} materialized records",
                    )
                payload = _safe_payload(dataset.dataset_type, raw)
                record_key = _record_key(dataset.dataset_type, payload, path, ordinal)
                if record_key in seen_keys:
                    raise ReferenceMaterializationError("duplicate_record_key", f"Duplicate runtime record key: {record_key}")
                seen_keys.add(record_key)
                if dataset.dataset_type == ReferenceDataset.DatasetType.GTIN_PRODUCT:
                    gtin = _technical_value(payload.get("gtin"))
                    if not _gtin_valid(gtin):
                        raise ReferenceMaterializationError("invalid_gtin", f"Invalid GTIN runtime record: {gtin or record_key}")
                lookup_key = normalize_reference_term(record_key)[:255]
                record = ReferenceDatasetRecord(
                    dataset=dataset,
                    record_key=record_key,
                    source_path=path,
                    ordinal=ordinal,
                    payload=payload,
                    lookup_key=lookup_key,
                    tombstone=_tombstone(payload),
                )
                record_batch.append(record)
                if not record.tombstone:
                    term_batch.extend(
                        ReferenceDatasetSearchTerm(dataset=dataset, record=record, term=term, kind=kind)
                        for term, kind in _terms_for(dataset.dataset_type, payload, record_key)
                    )
                if len(record_batch) >= 500:
                    flush()
        flush()
    return count


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


def _active_records(dataset_type, dataset_id=None):
    queryset = ReferenceDatasetRecord.objects.filter(
        dataset__state=ReferenceDataset.State.ACTIVE,
        dataset__redistribution__in=_RUNTIME_REDISTRIBUTION,
        dataset__validation_summary__runtime_eligible=True,
        dataset__dataset_type=dataset_type,
        tombstone=False,
    ).select_related("dataset")
    if dataset_id:
        queryset = queryset.filter(dataset__dataset_id=dataset_id)
    return queryset


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
        },
    }


def search_reference_records(*, dataset_type, query, dataset_id=None, limit=None, offset=None):
    dataset_type = _dataset_type(dataset_type)
    dataset_id = _dataset_id(dataset_id)
    limit = _limit(limit)
    offset = _offset(offset)
    query = normalize_reference_term(query)
    if len(query) < 2 or len(query) > MAX_QUERY_LENGTH:
        raise ReferenceReadError("invalid_query", f"query length must be between 2 and {MAX_QUERY_LENGTH}")

    exact = ReferenceDatasetSearchTerm.objects.filter(record_id=OuterRef("pk"), term=query)
    queryset = (
        _active_records(dataset_type, dataset_id)
        .filter(search_terms__term__startswith=query)
        .annotate(exact_match=Exists(exact))
        .distinct()
        .order_by("-exact_match", "lookup_key", "record_key", "id")
    )
    rows = list(queryset[offset : offset + limit + 1])
    has_more = len(rows) > limit
    rows = rows[:limit]
    return {
        "results": [serialize_reference_record(row) for row in rows],
        "limit": limit,
        "offset": offset,
        "next_offset": offset + limit if has_more and offset + limit <= MAX_QUERY_OFFSET else None,
    }


def lookup_reference_records(*, dataset_type, key, dataset_id=None, limit=10):
    dataset_type = _dataset_type(dataset_type)
    dataset_id = _dataset_id(dataset_id)
    limit = min(_limit(limit), 10)
    key = normalize_reference_term(key)
    if not key or len(key) > 255:
        raise ReferenceReadError("invalid_key", "lookup key is required and must fit the runtime key budget")
    rows = list(_active_records(dataset_type, dataset_id).filter(lookup_key=key).order_by("record_key", "id")[:limit])
    return {"results": [serialize_reference_record(row) for row in rows], "limit": limit}
