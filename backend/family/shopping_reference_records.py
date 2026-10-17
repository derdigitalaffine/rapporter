import csv
import io
import json
import re
import unicodedata
from pathlib import PurePosixPath

from django.db import transaction

from .shopping_reference_models import (
    ReferenceDataset,
    ReferenceDatasetRecord,
    ReferenceDatasetSearchTerm,
)


MAX_MATERIALIZED_RECORDS = 100_000
MAX_RECORD_JSON_BYTES = 32 * 1024
MAX_TERMS_PER_RECORD = 64
MAX_TOTAL_SEARCH_TERMS = 500_000
MAX_TERM_LENGTH = 200
_TOMBSTONE_STATUSES = {"deleted", "removed", "tombstone"}
_WHITESPACE_RE = re.compile(r"\s+")

_COMMON_FIELDS = {"status", "tombstone", "deleted"}
_ALLOWED_FIELDS = {
    ReferenceDataset.DatasetType.STORE_REFERENCE: _COMMON_FIELDS
    | {
        "id", "store_id", "chain_id", "sample_id", "canonical_name", "name", "aliases",
        "operator_scope", "country_region", "wikidata_id", "nsi_id", "location_provider",
        "location_ref", "branch_label", "address", "city", "postcode", "latitude", "longitude",
        "source_namespace", "source_id", "source_revision", "verified_at", "confidence", "source_status",
        "public_place_hint",
    },
    ReferenceDataset.DatasetType.LEXICON: _COMMON_FIELDS
    | {
        "id", "label_de", "label", "name", "parent_id", "shopping_department", "aliases", "synonyms",
        "negative_terms", "ambiguity", "provenance",
    },
    ReferenceDataset.DatasetType.GTIN_PRODUCT: _COMMON_FIELDS
    | {
        "id", "gtin", "ean", "product_name", "name", "brand", "quantity", "source_category",
        "mapped_category_id", "source_namespace", "source_id", "source_revision", "countries_evidence",
        "verified_at", "confidence",
    },
    ReferenceDataset.DatasetType.STORE_LAYOUT_EVIDENCE: _COMMON_FIELDS
    | {
        "id", "evidence_id", "layout_id", "store_ref", "store_id", "chain_id", "section_id", "section",
        "aisle", "category_id", "category", "position", "source_namespace", "source_id", "source_revision",
        "valid_from", "valid_to", "verified_at", "confidence", "evidence",
    },
}
_PRIMARY_FIELDS = (
    "label_de", "label", "name", "display_name", "canonical_name", "product_name", "section", "category",
    "aisle", "public_place_hint", "value",
)
_ALIAS_FIELDS = ("aliases", "synonyms")
_CODE_FIELDS = ("gtin", "ean", "wikidata_id", "nsi_id", "source_id", "location_ref", "mapped_category_id")
_ID_FIELDS = (
    "id", "key", "slug", "evidence_id", "layout_id", "store_id", "chain_id", "sample_id", "section_id",
    "category_id",
)
_RECORD_KEY_FIELDS = (
    "id", "gtin", "ean", "key", "slug", "evidence_id", "layout_id", "sample_id", "store_id", "section_id",
    "chain_id", "category_id",
)
_LOOKUP_FIELDS = (
    "gtin", "ean", "label_de", "label", "name", "display_name", "canonical_name", "product_name", "id", "key",
    "store_id", "chain_id",
)


class ReferenceRecordMaterializationError(ValueError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def normalize_reference_term(value):
    if value is None:
        return ""
    if not isinstance(value, str):
        value = str(value)
    value = unicodedata.normalize("NFKC", value).casefold().strip()
    return _WHITESPACE_RE.sub(" ", value)[:MAX_TERM_LENGTH]


def _error(code, message):
    raise ReferenceRecordMaterializationError(code, message)


def _json_size(value):
    try:
        encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ReferenceRecordMaterializationError("invalid_record", "Reference record is not JSON serializable") from exc
    if len(encoded) > MAX_RECORD_JSON_BYTES:
        _error("record_too_large", f"Reference record exceeds {MAX_RECORD_JSON_BYTES} bytes")
    return encoded


def _as_record(value):
    if not isinstance(value, dict):
        _error("invalid_record_schema", "Reference runtime records must be objects")
    return dict(value)


def _append_bounded(rows, value, path):
    if len(rows) >= MAX_MATERIALIZED_RECORDS:
        _error("too_many_runtime_records", f"{path} exceeds the runtime record budget")
    rows.append(_as_record(value))


def _records_from_file(path, content):
    suffix = PurePosixPath(path).suffix.lower()
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ReferenceRecordMaterializationError("invalid_encoding", f"{path} must be UTF-8 text") from exc

    if suffix == ".csv":
        try:
            reader = csv.DictReader(io.StringIO(text))
            fieldnames = reader.fieldnames or []
            if not fieldnames or any(not str(name or "").strip() for name in fieldnames) or len(set(fieldnames)) != len(fieldnames):
                _error("invalid_record_schema", f"{path} requires unique non-empty CSV headers")
            rows = []
            for row in reader:
                _append_bounded(rows, row, path)
            return rows
        except csv.Error as exc:
            raise ReferenceRecordMaterializationError("invalid_data", f"Invalid CSV: {path}") from exc
    if suffix == ".jsonl":
        rows = []
        for line_number, line in enumerate(text.splitlines(), start=1):
            if not line.strip():
                continue
            try:
                _append_bounded(rows, json.loads(line), path)
            except json.JSONDecodeError as exc:
                raise ReferenceRecordMaterializationError("invalid_data", f"Invalid JSONL at {path}:{line_number}") from exc
        return rows
    if suffix == ".json":
        try:
            value = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ReferenceRecordMaterializationError("invalid_data", f"Invalid JSON: {path}") from exc
        if isinstance(value, list):
            rows = []
            for row in value:
                _append_bounded(rows, row, path)
            return rows
        if isinstance(value, dict):
            for key in ("entries", "items", "products", "records"):
                nested = value.get(key)
                if isinstance(nested, list):
                    rows = []
                    for row in nested:
                        _append_bounded(rows, row, path)
                    return rows
            return [_as_record(value)]
        _error("invalid_record_schema", f"{path} must contain objects or an object list")
    if suffix == ".txt":
        _error("unsupported_runtime_format", f"Plain text files cannot be materialized as typed runtime records: {path}")
    _error("unsupported_format", f"Unsupported reference file: {path}")


def _sanitize_record(dataset, record, source_path):
    allowed = _ALLOWED_FIELDS.get(dataset.dataset_type)
    if allowed is None:
        _error("unsupported_dataset_type", f"No runtime record contract for {dataset.dataset_type}")
    payload = {key: value for key, value in record.items() if key in allowed and value not in (None, "")}
    meaningful = set(payload) - _COMMON_FIELDS
    if not meaningful:
        _error("unsupported_record_shape", f"{source_path} contains no supported {dataset.dataset_type} fields")
    _json_size(payload)
    return payload


def _scalar(record, field):
    value = record.get(field)
    if isinstance(value, bool) or value is None:
        return ""
    if isinstance(value, (str, int)):
        return str(value).strip()
    return ""


def _record_key(record, source_path, ordinal):
    for field in _RECORD_KEY_FIELDS:
        value = _scalar(record, field)
        if value:
            key = f"{field}:{value}"
            if len(key) > 256:
                _error("record_key_too_long", f"Stable record key exceeds 256 characters in {source_path}")
            return key
    fallback = f"{source_path}:{ordinal}"
    if len(fallback) > 256:
        _error("record_key_too_long", f"Fallback record key exceeds 256 characters in {source_path}")
    return fallback


def _lookup_key(record):
    for field in _LOOKUP_FIELDS:
        value = _scalar(record, field)
        if value:
            return normalize_reference_term(value)[:255]
    return ""


def _is_tombstone(record):
    if record.get("tombstone") is True or record.get("deleted") is True:
        return True
    return normalize_reference_term(record.get("status")) in _TOMBSTONE_STATUSES


def _gtin_is_valid(value):
    if not isinstance(value, str) or not value.isdigit() or len(value) not in {8, 12, 13, 14}:
        return False
    body = value[:-1]
    check_digit = int(value[-1])
    total = 0
    weight = 3
    for char in reversed(body):
        total += int(char) * weight
        weight = 1 if weight == 3 else 3
    return (10 - (total % 10)) % 10 == check_digit


def _validate_dataset_record(dataset, record, source_path):
    if dataset.dataset_type == ReferenceDataset.DatasetType.LEXICON:
        if dataset.quality.get("ambiguous_input_policy") != "ABSTAIN":
            _error("lexicon_policy", "Lexicon packages must declare ambiguous_input_policy=ABSTAIN")
    if dataset.dataset_type == ReferenceDataset.DatasetType.GTIN_PRODUCT and not _is_tombstone(record):
        gtin = _scalar(record, "gtin") or _scalar(record, "ean")
        if not _gtin_is_valid(gtin):
            _error("invalid_gtin", f"GTIN/EAN in {source_path} must be a valid GTIN-8/12/13/14 string")


def _alias_values(value):
    if value is None:
        return []
    if isinstance(value, list):
        values = value
    elif isinstance(value, str):
        values = re.split(r"[|;]", value)
    else:
        _error("invalid_aliases", "aliases/synonyms must be a list or a |/;-separated string")
    result = []
    for item in values:
        if not isinstance(item, str):
            _error("invalid_aliases", "alias entries must be strings")
        item = item.strip()
        if item:
            result.append(item)
    return result


def _search_terms(record):
    terms = []
    seen = set()

    def add(value, kind):
        normalized = normalize_reference_term(value)
        if not normalized or normalized in seen:
            return
        if len(terms) >= MAX_TERMS_PER_RECORD:
            _error("too_many_terms", f"Reference record exceeds {MAX_TERMS_PER_RECORD} search terms")
        seen.add(normalized)
        terms.append((normalized, kind))

    for field in _PRIMARY_FIELDS:
        value = _scalar(record, field)
        if value:
            add(value, ReferenceDatasetSearchTerm.Kind.PRIMARY)
    for field in _ALIAS_FIELDS:
        for value in _alias_values(record.get(field)):
            add(value, ReferenceDatasetSearchTerm.Kind.ALIAS)
    for field in _CODE_FIELDS:
        value = _scalar(record, field)
        if value:
            add(value, ReferenceDatasetSearchTerm.Kind.CODE)
    for field in _ID_FIELDS:
        value = _scalar(record, field)
        if value:
            add(value, ReferenceDatasetSearchTerm.Kind.ID)
    return terms


def materialize_reference_dataset(dataset, payload_files):
    """Atomically replace one immutable public package version's typed runtime records and terms."""
    if not isinstance(payload_files, dict):
        _error("invalid_payload", "payload_files must be a mapping")

    record_objects = []
    term_specs = []
    seen_keys = set()
    total_terms = 0
    ordinal = 0
    for source_path in sorted(payload_files):
        rows = _records_from_file(source_path, payload_files[source_path])
        for raw_record in rows:
            ordinal += 1
            if ordinal > MAX_MATERIALIZED_RECORDS:
                _error("too_many_runtime_records", f"Package exceeds {MAX_MATERIALIZED_RECORDS} materialized records")
            record = _sanitize_record(dataset, raw_record, source_path)
            _validate_dataset_record(dataset, record, source_path)
            record_key = _record_key(record, source_path, ordinal)
            if record_key in seen_keys:
                _error("duplicate_record_key", f"Duplicate stable record key: {record_key}")
            seen_keys.add(record_key)
            tombstone = _is_tombstone(record)
            record_object = ReferenceDatasetRecord(
                dataset=dataset,
                record_key=record_key,
                source_path=source_path,
                ordinal=ordinal,
                payload=record,
                lookup_key=_lookup_key(record),
                tombstone=tombstone,
            )
            record_objects.append(record_object)
            if not tombstone:
                terms = _search_terms(record)
                total_terms += len(terms)
                if total_terms > MAX_TOTAL_SEARCH_TERMS:
                    _error("too_many_search_terms", f"Package exceeds {MAX_TOTAL_SEARCH_TERMS} materialized search terms")
                term_specs.append((record_object, terms))

    with transaction.atomic():
        ReferenceDatasetSearchTerm.objects.filter(dataset=dataset).delete()
        ReferenceDatasetRecord.objects.filter(dataset=dataset).delete()
        ReferenceDatasetRecord.objects.bulk_create(record_objects, batch_size=500)
        term_batch = []
        for record_object, terms in term_specs:
            for term, kind in terms:
                term_batch.append(
                    ReferenceDatasetSearchTerm(
                        dataset=dataset,
                        record=record_object,
                        term=term,
                        kind=kind,
                    )
                )
                if len(term_batch) >= 1000:
                    ReferenceDatasetSearchTerm.objects.bulk_create(term_batch, batch_size=1000)
                    term_batch = []
        if term_batch:
            ReferenceDatasetSearchTerm.objects.bulk_create(term_batch, batch_size=1000)

    return {
        "records": len(record_objects),
        "search_terms": total_terms,
        "tombstones": sum(1 for record in record_objects if record.tombstone),
    }
