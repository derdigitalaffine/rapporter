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


MAX_RECORD_JSON_BYTES = 32 * 1024
MAX_TERMS_PER_RECORD = 64
MAX_TERM_LENGTH = 200
_PRIMARY_FIELDS = ("label_de", "label", "name", "display_name", "value")
_ALIAS_FIELDS = ("aliases", "synonyms")
_CODE_FIELDS = ("gtin", "ean")
_ID_FIELDS = ("id", "key", "slug", "store_id", "chain_id")
_RECORD_KEY_FIELDS = ("id", "gtin", "ean", "key", "slug", "store_id", "chain_id")
_LOOKUP_FIELDS = ("gtin", "ean", "label_de", "label", "name", "display_name", "id", "key")
_WHITESPACE_RE = re.compile(r"\s+")


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
    if isinstance(value, dict):
        record = dict(value)
    else:
        record = {"value": value}
    _json_size(record)
    return record


def _records_from_file(path, content):
    suffix = PurePosixPath(path).suffix.lower()
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ReferenceRecordMaterializationError("invalid_encoding", f"{path} must be UTF-8 text") from exc

    if suffix == ".csv":
        try:
            return [_as_record(row) for row in csv.DictReader(io.StringIO(text))]
        except csv.Error as exc:
            raise ReferenceRecordMaterializationError("invalid_data", f"Invalid CSV: {path}") from exc
    if suffix == ".jsonl":
        rows = []
        for line in text.splitlines():
            if not line.strip():
                continue
            try:
                rows.append(_as_record(json.loads(line)))
            except json.JSONDecodeError as exc:
                raise ReferenceRecordMaterializationError("invalid_data", f"Invalid JSONL: {path}") from exc
        return rows
    if suffix == ".txt":
        return [_as_record({"value": line.strip()}) for line in text.splitlines() if line.strip()]
    if suffix == ".json":
        try:
            value = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ReferenceRecordMaterializationError("invalid_data", f"Invalid JSON: {path}") from exc
        if isinstance(value, list):
            return [_as_record(row) for row in value]
        if isinstance(value, dict):
            for key in ("entries", "items", "products", "records"):
                nested = value.get(key)
                if isinstance(nested, list):
                    return [_as_record(row) for row in nested]
            return [_as_record(value)]
    _error("unsupported_format", f"Unsupported reference file: {path}")


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
    return record.get("tombstone") is True or record.get("deleted") is True


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
        values = record.get(field)
        if values is None:
            continue
        if not isinstance(values, list):
            _error("invalid_aliases", f"{field} must be a list")
        for value in values:
            if not isinstance(value, str):
                _error("invalid_aliases", f"{field} entries must be strings")
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
    """Atomically replace one immutable public package version's records and terms."""
    if not isinstance(payload_files, dict):
        _error("invalid_payload", "payload_files must be a mapping")

    record_objects = []
    term_specs = []
    seen_keys = set()
    ordinal = 0
    for source_path in sorted(payload_files):
        rows = _records_from_file(source_path, payload_files[source_path])
        for record in rows:
            ordinal += 1
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
                term_specs.append((record_object, _search_terms(record)))

    with transaction.atomic():
        ReferenceDatasetSearchTerm.objects.filter(dataset=dataset).delete()
        ReferenceDatasetRecord.objects.filter(dataset=dataset).delete()
        ReferenceDatasetRecord.objects.bulk_create(record_objects, batch_size=500)
        term_objects = []
        for record_object, terms in term_specs:
            for term, kind in terms:
                term_objects.append(
                    ReferenceDatasetSearchTerm(
                        dataset=dataset,
                        record=record_object,
                        term=term,
                        kind=kind,
                    )
                )
        if term_objects:
            ReferenceDatasetSearchTerm.objects.bulk_create(term_objects, batch_size=1000)

    return {
        "records": len(record_objects),
        "search_terms": sum(len(terms) for _record, terms in term_specs),
        "tombstones": sum(1 for record in record_objects if record.tombstone),
    }
