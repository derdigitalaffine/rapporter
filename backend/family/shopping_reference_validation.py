import csv
import hashlib
import io
import json
import re
import stat
import zipfile
from pathlib import PurePosixPath
from urllib.parse import urlparse

from django.utils import timezone

from .shopping_reference_models import ReferenceDataset
from .shopping_reference_records import (
    ReferenceRecordMaterializationError,
    materialize_reference_dataset,
)


MAX_PACKAGE_BYTES = 10 * 1024 * 1024
MAX_MANIFEST_BYTES = 256 * 1024
MAX_FILES = 64
MAX_SINGLE_FILE_BYTES = 8 * 1024 * 1024
MAX_UNCOMPRESSED_BYTES = 32 * 1024 * 1024
MAX_COMPRESSION_RATIO = 100
ALLOWED_SUFFIXES = {".csv", ".json", ".jsonl", ".txt"}
SOURCE_ADAPTERS = frozenset({"repository_fixture", "operator_upload"})

_DATASET_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{2,179}$")
_VERSION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+\-]{0,79}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_CONTENT_CHECKSUM_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_STABLE_VALID_STATES = {
    ReferenceDataset.State.PREVIEW,
    ReferenceDataset.State.ACTIVE,
    ReferenceDataset.State.DISABLED,
    ReferenceDataset.State.STALE,
}


class ReferencePackageError(ValueError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


class ReferencePackageVersionConflict(ReferencePackageError):
    pass


def reference_content_checksum(files):
    """Checksum the immutable package payload without self-hashing manifest.json."""
    digest = hashlib.sha256()
    for path in sorted(files):
        file_digest = hashlib.sha256(files[path]).hexdigest()
        digest.update(path.encode("utf-8"))
        digest.update(b"\0")
        digest.update(file_digest.encode("ascii"))
        digest.update(b"\n")
    return f"sha256:{digest.hexdigest()}"


def _manifest_fingerprint(manifest):
    canonical = json.dumps(
        manifest,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _error(code, message):
    raise ReferencePackageError(code, message)


def _bounded_text(value, field, max_length, *, required=False):
    if value is None:
        value = ""
    if not isinstance(value, str):
        _error("invalid_manifest", f"{field} must be a string")
    value = value.strip()
    if required and not value:
        _error("invalid_manifest", f"{field} is required")
    if len(value) > max_length:
        _error("invalid_manifest", f"{field} exceeds {max_length} characters")
    return value


def _validate_member_path(name):
    if not name or "\\" in name:
        _error("unsafe_archive_path", f"Unsafe archive path: {name!r}")
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts:
        _error("unsafe_archive_path", f"Unsafe archive path: {name!r}")
    return path


def _read_bounded_archive(package_bytes):
    if not isinstance(package_bytes, (bytes, bytearray)):
        _error("invalid_package", "Package must be bytes")
    package_bytes = bytes(package_bytes)
    if not package_bytes:
        _error("invalid_package", "Package is empty")
    if len(package_bytes) > MAX_PACKAGE_BYTES:
        _error("package_too_large", f"Package exceeds {MAX_PACKAGE_BYTES} bytes")

    try:
        archive = zipfile.ZipFile(io.BytesIO(package_bytes), "r")
    except zipfile.BadZipFile as exc:
        raise ReferencePackageError("malformed_archive", "Package is not a valid ZIP archive") from exc

    with archive:
        infos = archive.infolist()
        if len(infos) > MAX_FILES:
            _error("too_many_files", f"Package contains more than {MAX_FILES} archive entries")

        names = set()
        total_uncompressed = 0
        readable = {}
        manifest_info = None
        for info in infos:
            path = _validate_member_path(info.filename)
            if info.filename in names:
                _error("duplicate_archive_path", f"Duplicate archive path: {info.filename}")
            names.add(info.filename)
            if info.is_dir():
                continue
            mode = info.external_attr >> 16
            if stat.S_ISLNK(mode):
                _error("archive_symlink", f"Symlinks are not allowed: {info.filename}")
            if info.flag_bits & 0x1:
                _error("encrypted_archive", f"Encrypted entries are not allowed: {info.filename}")
            if info.file_size > MAX_SINGLE_FILE_BYTES:
                _error("file_too_large", f"Archive entry exceeds {MAX_SINGLE_FILE_BYTES} bytes: {info.filename}")
            total_uncompressed += info.file_size
            if total_uncompressed > MAX_UNCOMPRESSED_BYTES:
                _error("archive_too_large", f"Uncompressed package exceeds {MAX_UNCOMPRESSED_BYTES} bytes")
            if info.file_size > 4096:
                ratio = info.file_size / max(info.compress_size, 1)
                if ratio > MAX_COMPRESSION_RATIO:
                    _error("compression_ratio", f"Suspicious compression ratio for {info.filename}")

            if path == PurePosixPath("manifest.json"):
                if info.file_size > MAX_MANIFEST_BYTES:
                    _error("manifest_too_large", f"manifest.json exceeds {MAX_MANIFEST_BYTES} bytes")
                manifest_info = info
            elif path.suffix.lower() not in ALLOWED_SUFFIXES:
                _error("unsupported_format", f"Unsupported package file type: {info.filename}")
            readable[info.filename] = info

        if manifest_info is None:
            _error("missing_manifest", "Package must contain manifest.json at archive root")

        payload_files = {}
        for name, info in readable.items():
            try:
                content = archive.read(info)
            except (RuntimeError, zipfile.BadZipFile, OSError) as exc:
                raise ReferencePackageError("archive_read_error", f"Could not read {name}") from exc
            if len(content) != info.file_size:
                _error("archive_size_mismatch", f"Archive entry size changed while reading: {name}")
            if name != "manifest.json":
                payload_files[name] = content

        try:
            manifest = json.loads(archive.read(manifest_info).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ReferencePackageError("invalid_manifest", "manifest.json must be UTF-8 JSON") from exc

    if not isinstance(manifest, dict):
        _error("invalid_manifest", "manifest.json must contain a JSON object")
    return package_bytes, manifest, payload_files


def _normalize_manifest(manifest):
    schema_version = manifest.get("schema_version")
    if schema_version != 1:
        _error("unsupported_schema", "Only reference package schema_version=1 is supported")

    dataset_id = _bounded_text(manifest.get("dataset_id"), "dataset_id", 180, required=True)
    if not _DATASET_ID_RE.fullmatch(dataset_id):
        _error("invalid_manifest", "dataset_id must be a stable lowercase semantic identifier")
    version = _bounded_text(manifest.get("version"), "version", 80, required=True)
    if not _VERSION_RE.fullmatch(version):
        _error("invalid_manifest", "version contains unsupported characters")

    dataset_type = manifest.get("dataset_type")
    allowed_types = {value for value, _label in ReferenceDataset.DatasetType.choices}
    if dataset_type not in allowed_types:
        _error("invalid_manifest", f"Unsupported dataset_type: {dataset_type!r}")

    redistribution = manifest.get("redistribution")
    allowed_redistribution = {value for value, _label in ReferenceDataset.Redistribution.choices}
    if redistribution not in allowed_redistribution:
        _error("invalid_manifest", f"Unsupported redistribution policy: {redistribution!r}")

    licence = _bounded_text(manifest.get("licence"), "licence", 120, required=True)
    attribution = _bounded_text(manifest.get("attribution"), "attribution", 10000)
    source_url = _bounded_text(manifest.get("source_url"), "source_url", 1000)
    if source_url:
        parsed = urlparse(source_url)
        if parsed.scheme != "https" or not parsed.netloc:
            _error("invalid_manifest", "source_url is metadata only but must be an absolute HTTPS URL")
    source_revision = _bounded_text(manifest.get("source_revision"), "source_revision", 200)
    locale = _bounded_text(manifest.get("locale"), "locale", 32)
    country = _bounded_text(manifest.get("country"), "country", 2)
    if country and (len(country) != 2 or country.upper() != country or not country.isalpha()):
        _error("invalid_manifest", "country must be an uppercase ISO-style two-letter code")
    region = _bounded_text(manifest.get("region"), "region", 120)

    content_checksum = manifest.get("checksum")
    if not isinstance(content_checksum, str) or not _CONTENT_CHECKSUM_RE.fullmatch(content_checksum):
        _error("invalid_manifest", "checksum must use sha256:<64 lowercase hex characters>")

    coverage = manifest.get("coverage", {})
    quality = manifest.get("quality", {})
    dependencies = manifest.get("dependencies", [])
    privacy = manifest.get("privacy")
    files = manifest.get("files")
    if not isinstance(coverage, dict) or not isinstance(quality, dict):
        _error("invalid_manifest", "coverage and quality must be JSON objects")
    if not isinstance(dependencies, list):
        _error("invalid_manifest", "dependencies must be a JSON list")
    if len(dependencies) > 32:
        _error("invalid_manifest", "dependencies exceeds 32 entries")
    if not isinstance(privacy, dict):
        _error("invalid_manifest", "privacy declaration is required")
    if not isinstance(files, list) or not files:
        _error("invalid_manifest", "files must be a non-empty JSON list")
    if len(files) > MAX_FILES - 1:
        _error("invalid_manifest", "files exceeds package entry limit")

    private_flags = {
        "contains_private_household_data",
        "contains_user_or_family_ids",
        "contains_private_family_corrections",
        "contains_household_observations",
    }
    for flag in private_flags:
        if privacy.get(flag) is True:
            _error("private_data", f"Public reference package declares private content: {flag}")

    if redistribution in {ReferenceDataset.Redistribution.ADOPT, ReferenceDataset.Redistribution.ADAPT}:
        if "unknown" in licence.lower() or "unreviewed" in licence.lower():
            _error("unreviewed_rights", "Runtime-eligible redistribution requires reviewed licence metadata")
    if redistribution == ReferenceDataset.Redistribution.ADAPT and not attribution:
        _error("missing_attribution", "Adapt redistribution requires attribution")

    return {
        "dataset_id": dataset_id,
        "dataset_type": dataset_type,
        "schema_version": schema_version,
        "version": version,
        "source_url": source_url,
        "source_revision": source_revision,
        "locale": locale,
        "country": country,
        "region": region,
        "licence": licence,
        "attribution": attribution,
        "redistribution": redistribution,
        "checksum": content_checksum,
        "coverage": coverage,
        "quality": quality,
        "dependencies": dependencies,
        "files": files,
    }


def _record_count(path, content):
    suffix = PurePosixPath(path).suffix.lower()
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ReferencePackageError("invalid_encoding", f"{path} must be UTF-8 text") from exc

    if suffix == ".csv":
        try:
            rows = list(csv.reader(io.StringIO(text)))
        except csv.Error as exc:
            raise ReferencePackageError("invalid_data", f"Invalid CSV: {path}") from exc
        return max(len(rows) - 1, 0)
    if suffix == ".jsonl":
        count = 0
        for line in text.splitlines():
            if not line.strip():
                continue
            try:
                json.loads(line)
            except json.JSONDecodeError as exc:
                raise ReferencePackageError("invalid_data", f"Invalid JSONL: {path}") from exc
            count += 1
        return count
    if suffix == ".txt":
        return sum(1 for line in text.splitlines() if line.strip())
    if suffix == ".json":
        try:
            value = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ReferencePackageError("invalid_data", f"Invalid JSON: {path}") from exc
        if isinstance(value, list):
            return len(value)
        if isinstance(value, dict):
            for key in ("entries", "items", "products", "records"):
                nested = value.get(key)
                if isinstance(nested, list):
                    return len(nested)
            return 1
    return 0


def _validate_payload(normalized, manifest, payload_files):
    specs = normalized["files"]
    declared_paths = set()
    counts = {}
    for spec in specs:
        if not isinstance(spec, dict):
            _error("invalid_manifest", "Each files entry must be an object")
        path = _bounded_text(spec.get("path"), "files.path", 500, required=True)
        _validate_member_path(path)
        if path == "manifest.json":
            _error("invalid_manifest", "manifest.json must not list itself as payload")
        if PurePosixPath(path).suffix.lower() not in ALLOWED_SUFFIXES:
            _error("unsupported_format", f"Unsupported package file type: {path}")
        if path in declared_paths:
            _error("invalid_manifest", f"Duplicate files entry: {path}")
        declared_paths.add(path)
        expected_sha = spec.get("sha256")
        if not isinstance(expected_sha, str) or not _SHA256_RE.fullmatch(expected_sha):
            _error("invalid_manifest", f"files.sha256 must be lowercase SHA-256 for {path}")
        expected_records = spec.get("records")
        if not isinstance(expected_records, int) or isinstance(expected_records, bool) or expected_records < 0:
            _error("invalid_manifest", f"files.records must be a non-negative integer for {path}")
        content = payload_files.get(path)
        if content is None:
            _error("missing_file", f"Manifest file is missing from package: {path}")
        actual_sha = hashlib.sha256(content).hexdigest()
        if actual_sha != expected_sha:
            _error("checksum_mismatch", f"SHA-256 mismatch for {path}")
        actual_records = _record_count(path, content)
        if actual_records != expected_records:
            _error("record_count_mismatch", f"Record count mismatch for {path}: expected {expected_records}, got {actual_records}")
        counts[path] = actual_records

    extra_paths = set(payload_files) - declared_paths
    if extra_paths:
        _error("undeclared_file", f"Package contains undeclared files: {', '.join(sorted(extra_paths))}")

    actual_content_checksum = reference_content_checksum(payload_files)
    if actual_content_checksum != normalized["checksum"]:
        _error("checksum_mismatch", "Package content checksum does not match manifest")
    return counts, actual_content_checksum


def _validate_dependencies(dependencies):
    normalized_dependencies = []
    missing = []
    for dependency in dependencies:
        if not isinstance(dependency, dict):
            _error("invalid_manifest", "Each dependency must be an object")
        dataset_id = _bounded_text(dependency.get("dataset_id"), "dependencies.dataset_id", 180, required=True)
        version = _bounded_text(dependency.get("version"), "dependencies.version", 80, required=True)
        normalized_dependencies.append({"dataset_id": dataset_id, "version": version})
        available = ReferenceDataset.objects.filter(
            dataset_id=dataset_id,
            version=version,
            state__in=[ReferenceDataset.State.PREVIEW, ReferenceDataset.State.ACTIVE],
            redistribution__in=[ReferenceDataset.Redistribution.ADOPT, ReferenceDataset.Redistribution.ADAPT],
        ).exists()
        if not available:
            missing.append(f"{dataset_id}@{version}")
    if missing:
        _error("missing_dependency", f"Missing validated dependencies: {', '.join(missing)}")
    return normalized_dependencies


def _failure_summary(exc, *, package_sha256, source_adapter):
    return {
        "valid": False,
        "runtime_eligible": False,
        "blockers": [exc.code],
        "archive_sha256": package_sha256,
        "source_adapter": source_adapter,
    }


def stage_reference_package(package_bytes, *, source_adapter):
    """Stage, validate and materialize a bounded ZIP package without network access."""
    if source_adapter not in SOURCE_ADAPTERS:
        _error("unknown_source_adapter", "Reference packages must use a registered source adapter")

    package_bytes, manifest, payload_files = _read_bounded_archive(package_bytes)
    normalized = _normalize_manifest(manifest)
    package_sha256 = hashlib.sha256(package_bytes).hexdigest()
    manifest_fingerprint = _manifest_fingerprint(manifest)

    existing = ReferenceDataset.objects.filter(
        dataset_id=normalized["dataset_id"],
        version=normalized["version"],
    ).first()
    preserved_state = None
    if existing:
        same_manifest = _manifest_fingerprint(existing.manifest or {}) == manifest_fingerprint
        if existing.checksum != normalized["checksum"] or not same_manifest:
            raise ReferencePackageVersionConflict(
                "version_conflict",
                "A dataset version is immutable and already exists with different content or manifest metadata",
            )
        if existing.validation_summary.get("valid") and existing.state in _STABLE_VALID_STATES:
            preserved_state = existing.state
            if existing.validation_summary.get("materialized") is True:
                return existing

    values = {
        **{key: normalized[key] for key in (
            "dataset_type",
            "schema_version",
            "source_url",
            "source_revision",
            "locale",
            "country",
            "region",
            "licence",
            "attribution",
            "redistribution",
            "checksum",
            "coverage",
            "quality",
            "dependencies",
        )},
        "source_adapter": source_adapter,
        "manifest": manifest,
        "package_size_bytes": len(package_bytes),
        "installed_at": timezone.now(),
        "state": ReferenceDataset.State.STAGED,
    }
    if existing:
        dataset = existing
        if preserved_state is None:
            for field, value in values.items():
                setattr(dataset, field, value)
            dataset.validation_error = ""
            dataset.validation_summary = {}
            dataset.record_count = 0
            dataset.save()
    else:
        dataset = ReferenceDataset.objects.create(
            dataset_id=normalized["dataset_id"],
            version=normalized["version"],
            **values,
        )

    if preserved_state is None:
        dataset.state = ReferenceDataset.State.VALIDATING
        dataset.save(update_fields=["state", "updated_at"])

    try:
        counts, content_checksum = _validate_payload(normalized, manifest, payload_files)
        normalized_dependencies = _validate_dependencies(normalized["dependencies"])
        try:
            materialized = materialize_reference_dataset(dataset, payload_files)
        except ReferenceRecordMaterializationError as exc:
            raise ReferencePackageError(exc.code, str(exc)) from exc
        expected_records = sum(counts.values())
        if materialized["records"] != expected_records:
            _error(
                "materialized_count_mismatch",
                f"Materialized {materialized['records']} records, expected {expected_records}",
            )
        runtime_eligible = normalized["redistribution"] in {
            ReferenceDataset.Redistribution.ADOPT,
            ReferenceDataset.Redistribution.ADAPT,
        }
        blockers = [] if runtime_eligible else [f"redistribution_{normalized['redistribution']}"]
        dataset.dependencies = normalized_dependencies
        dataset.record_count = materialized["records"]
        dataset.validation_summary = {
            "valid": True,
            "runtime_eligible": runtime_eligible,
            "blockers": blockers,
            "archive_sha256": package_sha256,
            "manifest_sha256": manifest_fingerprint,
            "content_checksum": content_checksum,
            "files": counts,
            "records": dataset.record_count,
            "search_terms": materialized["search_terms"],
            "tombstones": materialized["tombstones"],
            "materialized": True,
            "source_adapter": dataset.source_adapter or source_adapter,
        }
        dataset.validation_error = ""
        dataset.validated_at = dataset.validated_at or timezone.now()
        dataset.state = preserved_state or ReferenceDataset.State.PREVIEW
        dataset.save(
            update_fields=[
                "dependencies",
                "record_count",
                "validation_summary",
                "validation_error",
                "validated_at",
                "state",
                "updated_at",
            ]
        )
        return dataset
    except ReferencePackageError as exc:
        if preserved_state is not None:
            raise
        dataset.state = ReferenceDataset.State.FAILED
        dataset.validation_error = str(exc)
        dataset.validation_summary = _failure_summary(
            exc,
            package_sha256=package_sha256,
            source_adapter=source_adapter,
        )
        dataset.save(update_fields=["state", "validation_error", "validation_summary", "updated_at"])
        return dataset
