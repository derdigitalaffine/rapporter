import csv
import hashlib
import io
import secrets
from collections import Counter
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.db.models import Q
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from .models import (
    PetCareLog,
    PetCareShare,
    PetHealthEvent,
    PetMedication,
    PetMedicationDose,
    PetObservation,
    PetReportExportAudit,
    PetWeightMeasurement,
    PetVetQuestion,
)

PUBLIC_CARE_KINDS = {
    PetCareLog.Kind.FEED,
    PetCareLog.Kind.WATER,
    PetCareLog.Kind.WALK,
    PetCareLog.Kind.TOILET,
    PetCareLog.Kind.GROOMING,
    PetCareLog.Kind.TRAINING,
    PetCareLog.Kind.NOTE,
}


def family_zone(family):
    try:
        return ZoneInfo(family.timezone or "Europe/Berlin")
    except ZoneInfoNotFoundError:
        return ZoneInfo("Europe/Berlin")


def record_care(pet, user, *, kind, occurred_at=None, ended_at=None, value=None, client_event_id=None, external_caregiver=""):
    if kind not in PetCareLog.Kind.values:
        raise ValidationError({"kind": "Unsupported care log kind."})
    occurred_at = occurred_at or timezone.now()
    if ended_at and ended_at < occurred_at:
        raise ValidationError({"ended_at": "End must be after start."})
    if client_event_id:
        existing = PetCareLog.objects.filter(pet=pet, client_event_id=client_event_id).first()
        if existing:
            return existing, False
    row = PetCareLog.objects.create(
        family=pet.family,
        pet=pet,
        kind=kind,
        occurred_at=occurred_at,
        ended_at=ended_at,
        value=value or {},
        created_by=user if getattr(user, "is_authenticated", False) else None,
        external_caregiver=external_caregiver[:120],
        client_event_id=client_event_id,
    )
    return row, True


def daily_due_medications(pet, at=None):
    at = at or timezone.now()
    zone = family_zone(pet.family)
    local = at.astimezone(zone)
    today = local.date()
    result = []
    meds = PetMedication.objects.filter(pet=pet, active=True, starts_at__lte=at).filter(Q(ends_at__isnull=True) | Q(ends_at__gte=at))
    for med in meds:
        times = med.schedule.get("times", []) if isinstance(med.schedule, dict) else []
        for clock in times:
            try:
                hour, minute = [int(part) for part in str(clock).split(":", 1)]
                scheduled_local = datetime.combine(today, time(hour, minute), tzinfo=zone)
            except (ValueError, TypeError):
                continue
            scheduled = scheduled_local.astimezone(timezone.get_current_timezone())
            exists = med.doses.filter(scheduled_for__date=scheduled.date(), state__in=[PetMedicationDose.State.GIVEN, PetMedicationDose.State.SKIPPED, PetMedicationDose.State.CANCELED]).exists()
            if not exists:
                result.append({
                    "medication": str(med.id),
                    "name": med.name,
                    "scheduled_for": scheduled.isoformat(),
                    "instruction_text": med.instruction_text,
                    "dose_value": str(med.dose_value) if med.dose_value is not None else None,
                    "dose_unit": med.dose_unit,
                })
    return sorted(result, key=lambda row: row["scheduled_for"])


def care_summary(pet, from_at, to_at):
    if not from_at or not to_at or from_at >= to_at:
        raise ValidationError("A valid from/to range is required.")
    if to_at - from_at > timedelta(days=93):
        raise ValidationError("Summary range is limited to 93 days.")
    logs = list(PetCareLog.objects.filter(pet=pet, occurred_at__gte=from_at, occurred_at__lte=to_at).select_related("created_by"))
    counts = Counter(row.kind for row in logs)
    walk_minutes = 0
    feed_amounts = []
    for row in logs:
        if row.kind == PetCareLog.Kind.WALK and row.ended_at:
            end = min(row.ended_at, to_at)
            start = max(row.occurred_at, from_at)
            walk_minutes += max(0, int((end - start).total_seconds() // 60))
        if row.kind == PetCareLog.Kind.FEED and isinstance(row.value, dict) and row.value.get("amount") is not None:
            try:
                feed_amounts.append(float(row.value["amount"]))
            except (ValueError, TypeError):
                pass
    doses = list(PetMedicationDose.objects.filter(
        medication__pet=pet,
        given_at__gte=from_at,
        given_at__lte=to_at,
        state=PetMedicationDose.State.GIVEN,
    ).select_related("medication", "given_by"))
    observations = list(PetObservation.objects.filter(pet=pet, observed_at__gte=from_at, observed_at__lte=to_at))
    latest = {}
    for row in logs:
        latest.setdefault(row.kind, row)
    return {
        "from_at": from_at.isoformat(),
        "to_at": to_at.isoformat(),
        "counts": dict(counts),
        "walk_minutes": walk_minutes,
        "feed_amount_total": round(sum(feed_amounts), 2) if feed_amounts else None,
        "medication_doses": len(doses),
        "observation_count": len(observations),
        "latest": {
            key: {
                "id": str(row.id),
                "occurred_at": row.occurred_at.isoformat(),
                "by": row.created_by.get_username() if row.created_by else row.external_caregiver,
                "value": row.value,
            }
            for key, row in latest.items()
        },
        "timeline": [
            {
                "id": str(row.id),
                "kind": row.kind,
                "occurred_at": row.occurred_at.isoformat(),
                "ended_at": row.ended_at.isoformat() if row.ended_at else None,
                "value": row.value,
                "by": row.created_by.get_username() if row.created_by else row.external_caregiver,
            }
            for row in logs[:200]
        ],
        "doses": [
            {
                "id": str(row.id),
                "medication": row.medication.name,
                "given_at": row.given_at.isoformat() if row.given_at else None,
                "by": row.given_by.get_username() if row.given_by else "",
            }
            for row in doses
        ],
        "observations": [
            {"id": str(row.id), "category": row.category, "severity": row.severity, "observed_at": row.observed_at.isoformat(), "note": row.note}
            for row in observations[:100]
        ],
        "open_medications": daily_due_medications(pet, to_at),
    }


def create_share(user, pet, *, permissions, starts_at, expires_at, label=""):
    if expires_at <= starts_at:
        raise ValidationError({"expires_at": "Expiry must be after start."})
    if expires_at - starts_at > timedelta(days=31):
        raise ValidationError({"expires_at": "Pet-care shares are limited to 31 days."})
    allowed = {
        "care": bool(permissions.get("care", True)),
        "medications": bool(permissions.get("medications", True)),
        "vet_contact": bool(permissions.get("vet_contact", True)),
        "emergency": bool(permissions.get("emergency", True)),
        "write_care": bool(permissions.get("write_care", False)),
    }
    raw = secrets.token_urlsafe(36)
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    share = PetCareShare.objects.create(
        family=pet.family,
        pet=pet,
        token_hash=digest,
        permissions=allowed,
        label=label[:120],
        starts_at=starts_at,
        expires_at=expires_at,
        created_by=user,
    )
    return share, raw


def share_from_token(token, *, touch=True):
    digest = hashlib.sha256(str(token or "").encode("utf-8")).hexdigest()
    now = timezone.now()
    share = PetCareShare.objects.select_related("pet__family").filter(token_hash=digest, revoked_at__isnull=True, starts_at__lte=now, expires_at__gt=now).first()
    if not share:
        return None
    if touch:
        PetCareShare.objects.filter(pk=share.pk).update(last_access_at=now)
        share.last_access_at = now
    return share


def emergency_card(pet, *, include_insurance=False):
    meds = PetMedication.objects.filter(pet=pet, active=True).order_by("name")
    payload = {
        "pet": {"id": str(pet.id), "name": pet.name, "species": pet.species, "breed": pet.breed, "color_description": pet.color_description},
        "microchip_id": pet.microchip_id,
        "allergies": pet.allergies,
        "important_notes": pet.important_notes,
        "primary_vet": {"name": pet.primary_vet_name, "phone": pet.primary_vet_phone},
        "emergency_contact": {"name": pet.emergency_contact_name, "phone": pet.emergency_contact_phone},
        "active_medications": [
            {"name": row.name, "instruction_text": row.instruction_text, "dose_value": str(row.dose_value) if row.dose_value is not None else None, "dose_unit": row.dose_unit}
            for row in meds
        ],
    }
    if include_insurance:
        payload["insurance"] = {"provider": pet.insurance_provider, "number": pet.insurance_number}
    return payload


def report_payload(pet, from_at, to_at, sections):
    selected = set(sections or [])
    allowed = {"care", "medications", "observations", "weights", "health", "documents", "questions"}
    if not selected:
        selected = {"medications", "observations", "weights", "health", "questions"}
    selected &= allowed
    payload = {"pet": {"id": str(pet.id), "name": pet.name, "species": pet.species}, "from_at": from_at.isoformat(), "to_at": to_at.isoformat(), "sections": sorted(selected)}
    if "care" in selected:
        payload["care"] = care_summary(pet, from_at, to_at)
    if "medications" in selected:
        payload["medications"] = [
            {
                "name": med.name,
                "instruction_text": med.instruction_text,
                "dose_value": str(med.dose_value) if med.dose_value is not None else None,
                "dose_unit": med.dose_unit,
                "doses": [
                    {"state": dose.state, "scheduled_for": dose.scheduled_for.isoformat() if dose.scheduled_for else None, "given_at": dose.given_at.isoformat() if dose.given_at else None}
                    for dose in med.doses.filter(Q(given_at__range=(from_at, to_at)) | Q(scheduled_for__range=(from_at, to_at)))
                ],
            }
            for med in PetMedication.objects.filter(pet=pet).prefetch_related("doses")
        ]
    if "observations" in selected:
        payload["observations"] = [
            {"category": row.category, "severity": row.severity, "observed_at": row.observed_at.isoformat(), "note": row.note}
            for row in PetObservation.objects.filter(pet=pet, observed_at__range=(from_at, to_at))
        ]
    if "weights" in selected:
        payload["weights"] = [
            {"measured_at": row.measured_at.isoformat(), "weight_kg": str(row.weight_kg), "source": row.source, "note": row.note}
            for row in PetWeightMeasurement.objects.filter(pet=pet, measured_at__range=(from_at, to_at))
        ]
    if "health" in selected:
        payload["health"] = [
            {"kind": row.kind, "title": row.title, "occurred_at": row.occurred_at.isoformat() if row.occurred_at else None, "next_due_at": row.next_due_at.isoformat() if row.next_due_at else None, "provider_name": row.provider_name, "note": row.note}
            for row in PetHealthEvent.objects.filter(pet=pet).filter(Q(occurred_at__range=(from_at, to_at)) | Q(next_due_at__range=(from_at, to_at)))
        ]
    if "documents" in selected:
        documents = pet.documents.filter(
            Q(occurred_at__range=(from_at.date(), to_at.date()))
            | Q(occurred_at__isnull=True, created_at__range=(from_at, to_at))
        )
        payload["documents"] = [
            {"id": str(row.id), "kind": row.kind, "title": row.title, "occurred_at": row.occurred_at.isoformat() if row.occurred_at else None, "provider_name": row.provider_name}
            for row in documents
        ]
    if "questions" in selected:
        payload["questions"] = [
            {"id": str(row.id), "question": row.question, "answered_at": row.answered_at.isoformat() if row.answered_at else None, "answer_note": row.answer_note}
            for row in PetVetQuestion.objects.filter(pet=pet, created_at__lte=to_at).filter(Q(answered_at__isnull=True) | Q(answered_at__gte=from_at))
        ]
    return payload


def report_csv(payload):
    output = io.StringIO()
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(["section", "timestamp", "kind", "value", "note"])
    care = payload.get("care") or {}
    for row in care.get("timeline", []):
        writer.writerow(["care", row.get("occurred_at"), row.get("kind"), row.get("value"), ""])
    for row in payload.get("observations", []):
        writer.writerow(["observation", row.get("observed_at"), row.get("category"), row.get("severity"), row.get("note")])
    for row in payload.get("weights", []):
        writer.writerow(["weight", row.get("measured_at"), "weight_kg", row.get("weight_kg"), row.get("note")])
    for row in payload.get("health", []):
        writer.writerow(["health", row.get("occurred_at") or row.get("next_due_at"), row.get("kind"), row.get("title"), row.get("note")])
    for row in payload.get("questions", []):
        writer.writerow(["question", row.get("answered_at") or "", "vet_question", row.get("question"), row.get("answer_note")])
    return output.getvalue()


def audit_report(pet, membership, export_format, sections, from_at, to_at):
    return PetReportExportAudit.objects.create(
        family=pet.family,
        pet=pet,
        membership=membership,
        export_format=export_format,
        sections=list(sections or []),
        range_start=from_at,
        range_end=to_at,
    )
