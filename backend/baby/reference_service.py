import hashlib
import json
import re
from datetime import date

from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError

from telemetry.service import try_record_audit_event

from .reference_models import PediatricReferencePackage


DEFAULT_SOURCE_KEY = "de_pediatric_standard"
KEY_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")

# Compatibility baseline until a reviewed package is published. This mirrors
# the previously server-side U-exam schedule; it is deliberately not presented
# as a published package and carries an explicit bundled version marker.
BUNDLED_U_EXAMS = [
    {"key": "U2", "start_day": 3, "end_day": 10, "target_day": 6, "window_label": "3.–10. Lebenstag"},
    {"key": "U3", "start_day": 21, "end_day": 35, "target_day": 31, "window_label": "4.–5. Lebenswoche"},
    {"key": "U4", "start_day": 91, "end_day": 122, "target_day": 105, "window_label": "3.–4. Lebensmonat"},
    {"key": "U5", "start_day": 183, "end_day": 213, "target_day": 198, "window_label": "6.–7. Lebensmonat"},
    {"key": "U6", "start_day": 304, "end_day": 365, "target_day": 335, "window_label": "10.–12. Lebensmonat"},
    {"key": "U7", "start_day": 639, "end_day": 730, "target_day": 685, "window_label": "21.–24. Lebensmonat"},
    {"key": "U7a", "start_day": 1035, "end_day": 1096, "target_day": 1065, "window_label": "34.–36. Lebensmonat"},
    {"key": "U8", "start_day": 1399, "end_day": 1461, "target_day": 1430, "window_label": "46.–48. Lebensmonat"},
    {"key": "U9", "start_day": 1826, "end_day": 1948, "target_day": 1887, "window_label": "60.–64. Lebensmonat"},
]
BUNDLED_SOURCE = {
    "package_id": None,
    "source_key": "gba_kinder_richtlinie",
    "source_title": "G-BA Kinder-Richtlinie",
    "source_version": "bundled-2026-01-01",
    "locale": "de-DE",
    "status": "bundled_fallback",
}


def require_superadmin(user):
    if not user or not getattr(user, "is_authenticated", False) or not getattr(user, "is_superuser", False):
        raise PermissionDenied("Superadmin access required.")
    return user


def canonical_payload(payload):
    try:
        return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    except (TypeError, ValueError) as exc:
        raise ValidationError({"payload": "Payload must be valid JSON."}) from exc


def payload_checksum(payload):
    return hashlib.sha256(canonical_payload(payload).encode("utf-8")).hexdigest()


def _require_key(value, field):
    value = str(value or "")
    if not KEY_RE.fullmatch(value):
        raise ValidationError({field: "Use a stable alphanumeric key with dots, dashes or underscores."})
    return value


def _validate_window(window, *, path):
    if not isinstance(window, dict):
        raise ValidationError({"payload": f"{path}.age_window must be an object."})
    try:
        start = int(window["start_day"])
        end = int(window["end_day"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValidationError({"payload": f"{path}.age_window requires integer start_day and end_day."}) from exc
    if start < 0 or end < start or end > 36500:
        raise ValidationError({"payload": f"{path}.age_window is not plausible."})
    target = window.get("target_day")
    if target is not None:
        try:
            target = int(target)
        except (TypeError, ValueError) as exc:
            raise ValidationError({"payload": f"{path}.age_window.target_day must be an integer."}) from exc
        if target < start or target > end:
            raise ValidationError({"payload": f"{path}.age_window.target_day must be inside the window."})
    return {"start_day": start, "end_day": end, "target_day": target if target is not None else (start + end) // 2}


def validate_reference_payload(payload):
    if not isinstance(payload, dict):
        raise ValidationError({"payload": "Payload must be an object."})
    if payload.get("schema_version") != 1:
        raise ValidationError({"payload": "schema_version must be 1."})

    exams = payload.get("u_exams", [])
    vaccinations = payload.get("vaccinations", [])
    if not isinstance(exams, list) or not isinstance(vaccinations, list):
        raise ValidationError({"payload": "u_exams and vaccinations must be arrays."})
    if not exams and not vaccinations:
        raise ValidationError({"payload": "At least one preventive or vaccination rule is required."})

    seen_exams = set()
    exam_preview = []
    for index, rule in enumerate(exams):
        if not isinstance(rule, dict):
            raise ValidationError({"payload": f"u_exams[{index}] must be an object."})
        key = _require_key(rule.get("key"), f"u_exams[{index}].key")
        if key in seen_exams:
            raise ValidationError({"payload": f"Duplicate preventive rule key: {key}."})
        seen_exams.add(key)
        window = _validate_window(rule.get("age_window"), path=f"u_exams[{index}]")
        display = rule.get("display", {})
        if display and not isinstance(display, dict):
            raise ValidationError({"payload": f"u_exams[{index}].display must be an object."})
        exam_preview.append({"key": key, **window})

    seen_vaccines = set()
    vaccine_preview = []
    for index, rule in enumerate(vaccinations):
        if not isinstance(rule, dict):
            raise ValidationError({"payload": f"vaccinations[{index}] must be an object."})
        key = _require_key(rule.get("key"), f"vaccinations[{index}].key")
        if key in seen_vaccines:
            raise ValidationError({"payload": f"Duplicate vaccination key: {key}."})
        seen_vaccines.add(key)
        doses = rule.get("doses")
        if not isinstance(doses, list) or not doses:
            raise ValidationError({"payload": f"vaccinations[{index}].doses must contain at least one dose."})
        sequences = set()
        dose_preview = []
        previous_sequence = 0
        for dose_index, dose in enumerate(doses):
            if not isinstance(dose, dict):
                raise ValidationError({"payload": f"vaccinations[{index}].doses[{dose_index}] must be an object."})
            try:
                sequence = int(dose["sequence"])
            except (KeyError, TypeError, ValueError) as exc:
                raise ValidationError({"payload": f"vaccinations[{index}].doses[{dose_index}].sequence must be an integer."}) from exc
            if sequence < 1 or sequence in sequences or sequence <= previous_sequence:
                raise ValidationError({"payload": f"{key} dose sequence must be unique and strictly increasing."})
            sequences.add(sequence)
            previous_sequence = sequence
            window = _validate_window(dose.get("age_window"), path=f"vaccinations[{index}].doses[{dose_index}]")
            min_interval = dose.get("min_interval_days", 0)
            try:
                min_interval = int(min_interval)
            except (TypeError, ValueError) as exc:
                raise ValidationError({"payload": f"{key} min_interval_days must be an integer."}) from exc
            if min_interval < 0 or min_interval > 3650:
                raise ValidationError({"payload": f"{key} min_interval_days is not plausible."})
            dose_preview.append({"sequence": sequence, "min_interval_days": min_interval, **window})
        boosters = rule.get("boosters", [])
        if not isinstance(boosters, list):
            raise ValidationError({"payload": f"vaccinations[{index}].boosters must be an array."})
        booster_preview = []
        for booster_index, booster in enumerate(boosters):
            if not isinstance(booster, dict):
                raise ValidationError({"payload": f"vaccinations[{index}].boosters[{booster_index}] must be an object."})
            booster_preview.append(_validate_window(booster.get("age_window"), path=f"vaccinations[{index}].boosters[{booster_index}]"))
        vaccine_preview.append({"key": key, "doses": dose_preview, "boosters": booster_preview})

    return {
        "schema_version": 1,
        "u_exams": exam_preview,
        "vaccinations": vaccine_preview,
        "u_exam_count": len(exam_preview),
        "vaccination_group_count": len(vaccine_preview),
    }


def serialize_reference_package(package, *, include_payload=True):
    value = {
        "id": str(package.id),
        "source_key": package.source_key,
        "source_title": package.source_title,
        "source_version": package.source_version,
        "locale": package.locale,
        "status": package.status,
        "published_at": package.published_at.isoformat() if package.published_at else None,
        "effective_from": package.effective_from.isoformat() if package.effective_from else None,
        "effective_to": package.effective_to.isoformat() if package.effective_to else None,
        "imported_at": package.imported_at.isoformat(),
        "checksum": package.checksum,
        "reason": package.reason,
        "notes": package.notes,
        "created_by": package.created_by_id,
        "published_by": package.published_by_id,
        "superseded_by": str(package.superseded_by_id) if package.superseded_by_id else None,
    }
    if include_payload:
        value["payload"] = package.payload
    return value


def create_reference_draft(
    user,
    *,
    source_key,
    source_title,
    source_version,
    locale="de-DE",
    payload,
    effective_from=None,
    effective_to=None,
    reason="",
    notes="",
):
    require_superadmin(user)
    source_key = _require_key(source_key, "source_key")
    source_title = str(source_title or "").strip()
    source_version = str(source_version or "").strip()
    locale = str(locale or "").strip()
    if not source_title or not source_version or not locale:
        raise ValidationError("source_title, source_version and locale are required.")
    if effective_from and effective_to and effective_to < effective_from:
        raise ValidationError({"effective_to": "effective_to must not be before effective_from."})
    return PediatricReferencePackage.objects.create(
        source_key=source_key,
        source_title=source_title[:200],
        source_version=source_version[:96],
        locale=locale[:16],
        status=PediatricReferencePackage.Status.DRAFT,
        effective_from=effective_from,
        effective_to=effective_to,
        imported_at=timezone.now(),
        checksum=payload_checksum(payload),
        payload=payload,
        reason=str(reason or "")[:240],
        notes=str(notes or ""),
        created_by=user,
    )


def update_reference_draft(package, user, **changes):
    require_superadmin(user)
    package.refresh_from_db()
    if package.status != PediatricReferencePackage.Status.DRAFT:
        raise ValidationError("Only draft pediatric reference packages can be edited.")
    allowed = {"source_title", "source_version", "locale", "payload", "effective_from", "effective_to", "reason", "notes"}
    unknown = set(changes) - allowed
    if unknown:
        raise ValidationError({"fields": f"Unsupported fields: {', '.join(sorted(unknown))}"})
    for field, value in changes.items():
        if field == "source_version":
            value = str(value or "").strip()[:96]
            if not value:
                raise ValidationError({"source_version": "source_version is required."})
        elif field == "source_title":
            value = str(value or "").strip()[:200]
            if not value:
                raise ValidationError({"source_title": "source_title is required."})
        elif field == "locale":
            value = str(value or "").strip()[:16]
            if not value:
                raise ValidationError({"locale": "locale is required."})
        elif field == "reason":
            value = str(value or "")[:240]
        elif field == "notes":
            value = str(value or "")
        setattr(package, field, value)
    if package.effective_from and package.effective_to and package.effective_to < package.effective_from:
        raise ValidationError({"effective_to": "effective_to must not be before effective_from."})
    if "payload" in changes:
        package.checksum = payload_checksum(package.payload)
    package.save()
    return package


def validate_reference_package(package):
    expected = payload_checksum(package.payload)
    if package.checksum != expected:
        raise ValidationError({"checksum": "Stored checksum does not match the immutable payload."})
    preview = validate_reference_payload(package.payload)
    return {
        "valid": True,
        "checksum": expected,
        "source_key": package.source_key,
        "source_version": package.source_version,
        "preview": preview,
    }


def _audit(event_key, user, package):
    try_record_audit_event(
        event_key,
        actor=user,
        actor_class="superadmin",
        outcome="success",
        reason="admin_action",
        target_type="reference_data",
        target_id=str(package.id),
        metadata={"source_key": package.source_key},
    )


def publish_reference_package(user, package_id):
    require_superadmin(user)
    with transaction.atomic():
        package = PediatricReferencePackage.objects.select_for_update().filter(pk=package_id).first()
        if not package:
            raise NotFound("Pediatric reference package not found.")
        if package.status != PediatricReferencePackage.Status.DRAFT:
            raise ValidationError("Only draft packages can be published.")
        validate_reference_package(package)
        previous = list(
            PediatricReferencePackage.objects.select_for_update().filter(
                source_key=package.source_key,
                locale=package.locale,
                status=PediatricReferencePackage.Status.PUBLISHED,
            ).exclude(pk=package.pk)
        )
        for old in previous:
            old.status = PediatricReferencePackage.Status.SUPERSEDED
            old.superseded_by = package
            old.save(update_fields=["status", "superseded_by", "updated_at"])
        package.status = PediatricReferencePackage.Status.PUBLISHED
        package.published_at = timezone.now()
        package.published_by = user
        package.save(update_fields=["status", "published_at", "published_by", "updated_at"])
    _audit("pediatric_reference.published", user, package)
    return package


def supersede_reference_package(user, package_id):
    require_superadmin(user)
    with transaction.atomic():
        package = PediatricReferencePackage.objects.select_for_update().filter(pk=package_id).first()
        if not package:
            raise NotFound("Pediatric reference package not found.")
        if package.status != PediatricReferencePackage.Status.PUBLISHED:
            raise ValidationError("Only a published package can be superseded.")
        package.status = PediatricReferencePackage.Status.SUPERSEDED
        package.superseded_by = None
        package.save(update_fields=["status", "superseded_by", "updated_at"])
    _audit("pediatric_reference.superseded", user, package)
    return package


def reactivate_reference_package(user, package_id):
    require_superadmin(user)
    with transaction.atomic():
        package = PediatricReferencePackage.objects.select_for_update().filter(pk=package_id).first()
        if not package:
            raise NotFound("Pediatric reference package not found.")
        if package.status != PediatricReferencePackage.Status.SUPERSEDED:
            raise ValidationError("Only a superseded package can be reactivated.")
        validate_reference_package(package)
        current = list(
            PediatricReferencePackage.objects.select_for_update().filter(
                source_key=package.source_key,
                locale=package.locale,
                status=PediatricReferencePackage.Status.PUBLISHED,
            ).exclude(pk=package.pk)
        )
        for old in current:
            old.status = PediatricReferencePackage.Status.SUPERSEDED
            old.superseded_by = package
            old.save(update_fields=["status", "superseded_by", "updated_at"])
        package.status = PediatricReferencePackage.Status.PUBLISHED
        package.superseded_by = None
        package.save(update_fields=["status", "superseded_by", "updated_at"])
    _audit("pediatric_reference.reactivated", user, package)
    return package


def published_reference_package(*, source_key=DEFAULT_SOURCE_KEY, locale="de-DE", on_date=None):
    on_date = on_date or timezone.localdate()
    queryset = PediatricReferencePackage.objects.filter(
        source_key=source_key,
        locale=locale,
        status=PediatricReferencePackage.Status.PUBLISHED,
    ).filter(Q(effective_from__isnull=True) | Q(effective_from__lte=on_date)).filter(Q(effective_to__isnull=True) | Q(effective_to__gte=on_date))
    return queryset.order_by("-effective_from", "-published_at", "-created_at").first()


def reference_package_by_id(package_id):
    package = PediatricReferencePackage.objects.filter(pk=package_id).first()
    if not package:
        raise NotFound("Pediatric reference package not found.")
    return package


def preventive_exam_rules(*, on_date=None, locale="de-DE"):
    package = published_reference_package(source_key=DEFAULT_SOURCE_KEY, locale=locale, on_date=on_date)
    if not package:
        return [dict(row, reference=dict(BUNDLED_SOURCE)) for row in BUNDLED_U_EXAMS]
    validate_reference_package(package)
    if not package.payload.get("u_exams"):
        return [dict(row, reference=dict(BUNDLED_SOURCE)) for row in BUNDLED_U_EXAMS]
    metadata = {
        "package_id": str(package.id),
        "source_key": package.source_key,
        "source_title": package.source_title,
        "source_version": package.source_version,
        "locale": package.locale,
        "status": package.status,
        "checksum": package.checksum,
    }
    rows = []
    for rule in package.payload.get("u_exams", []):
        window = _validate_window(rule.get("age_window"), path=f"u_exams.{rule.get('key', '?')}")
        display = rule.get("display") or {}
        rows.append(
            {
                "key": rule["key"],
                "start_day": window["start_day"],
                "end_day": window["end_day"],
                "target_day": window["target_day"],
                "window_label": display.get("window_label") or f"Tag {window['start_day']}–{window['end_day']}",
                "reference": dict(metadata),
            }
        )
    return sorted(rows, key=lambda row: (row["target_day"], row["key"]))


def all_preventive_exam_keys():
    keys = {row["key"] for row in BUNDLED_U_EXAMS}
    for payload in PediatricReferencePackage.objects.filter(
        status__in=[PediatricReferencePackage.Status.PUBLISHED, PediatricReferencePackage.Status.SUPERSEDED]
    ).values_list("payload", flat=True):
        if isinstance(payload, dict):
            for rule in payload.get("u_exams", []):
                if isinstance(rule, dict) and KEY_RE.fullmatch(str(rule.get("key") or "")):
                    keys.add(str(rule["key"]))
    return keys
