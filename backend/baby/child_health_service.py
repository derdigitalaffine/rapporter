from datetime import timedelta

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import APIException, ValidationError

from family.models import FamilyEvent
from .child_identity_service import child_scope_access
from .development_service import _private_event_token, _provenance_defaults
from .models import BabyProfile, ChildHealthRecord
from .pregnancy_service import local_date
from .reference_models import PediatricPreventiveEventReference
from .reference_service import preventive_exam_rules, published_reference_package, validate_reference_package, _validate_window


class HealthConflict(APIException):
    status_code = 409
    default_detail = "The record changed. Reload before saving."
    default_code = "version_conflict"


def health_rules(baby, language="de"):
    locale = "de-DE" if baby.family.locale.startswith("de") else baby.family.locale
    rows = [{**rule, "key": f"exam:{rule['key']}", "rule_key": rule["key"], "kind": "exam", "title": rule["key"]}
            for rule in preventive_exam_rules(locale=locale)]
    package = published_reference_package(locale=locale)
    if package:
        validate_reference_package(package)
        for group in package.payload.get("vaccinations", []):
            display = group.get("display") or {}
            title = display.get(language) or display.get("title") or group["key"] if isinstance(display, dict) else group["key"]
            reference = {"package_id": str(package.id), "source_key": package.source_key,
                         "source_version": package.source_version, "source_title": package.source_title,
                         "checksum": package.checksum, "locale": package.locale, "status": package.status}
            for index, dose in enumerate([*group.get("doses", []), *group.get("boosters", [])]):
                window = _validate_window(dose["age_window"], path=f"vaccinations.{group['key']}")
                sequence = str(dose.get("sequence") or f"booster-{index + 1}")
                rows.append({"key": f"vaccination:{group['key']}:{sequence}", "kind": "vaccination",
                             "rule_key": f"{group['key']}:{sequence}", "title": str(title), "dose": sequence,
                             "start_day": window["start_day"], "end_day": window["end_day"],
                             "target_day": window.get("target_day", window["start_day"]), "reference": reference})
    return rows, package


def serialize_record(row):
    return {"key": row.key, "kind": row.kind, "title": row.title, "state": row.state,
            "occurred_on": row.occurred_on.isoformat() if row.occurred_on else None,
            "planned_at": row.planned_at.isoformat() if row.planned_at else None,
            "practice": row.practice, "note": row.note, "batch": row.batch,
            "reference": row.reference, "event": str(row.event_id) if row.event_id else None, "version": row.version}


def health_payload(user, baby, language="de"):
    child_scope_access(user, baby, "development")
    rules, package = health_rules(baby, language)
    records = {row.key: row for row in baby.health_records.all()}
    age_days = (local_date(baby.family) - baby.birth_date).days
    items = []
    for rule in rules:
        record = records.pop(rule["key"], None)
        items.append({**rule, "historical": rule["end_day"] < age_days,
                      "window_start": (baby.birth_date + timedelta(days=rule["start_day"])).isoformat(),
                      "window_end": (baby.birth_date + timedelta(days=rule["end_day"])).isoformat(),
                      "state": "unknown", "version": 0, **(serialize_record(record) if record else {})})
    items.extend({**serialize_record(row), "historical": True} for row in records.values())
    return {"baby": str(baby.id), "items": items,
            "vaccination_reference_available": bool(package and package.payload.get("vaccinations")),
            "notice": "Recorded history and published references, not diagnosis or individual medical advice."}


@transaction.atomic
def save_health_record(user, baby, values):
    # Serialize competing create/update requests for the same child and key.
    baby = BabyProfile.objects.select_for_update(of=("self",)).select_related("family", "membership").get(pk=baby.id, active=True)
    child_scope_access(user, baby, "development")
    rules, _ = health_rules(baby)
    rule = next((row for row in rules if row["key"] == values["key"]), None)
    existing = ChildHealthRecord.objects.filter(baby=baby, key=values["key"]).first()
    if not rule and not existing and not values["key"].startswith("manual:"):
        raise ValidationError({"key": "Choose a current reference or a manual vaccination record."})
    if not existing and rule and "reference_checksum" in values and values["reference_checksum"] != rule["reference"].get("checksum", ""):
        raise HealthConflict("The reference changed. Reload before saving.")
    state = values["state"]
    occurred = values.get("occurred_on")
    planned = values.get("planned_at")
    if occurred and (occurred < baby.birth_date or occurred > local_date(baby.family)):
        raise ValidationError({"occurred_on": "Use a date between birth and today."})
    if state == "planned" and not planned:
        raise ValidationError({"planned_at": "Choose the actual appointment date and time."})
    if state == "planned" and planned < timezone.now():
        raise ValidationError({"planned_at": "Past history must not create a new appointment."})
    fields = {"state": state, "occurred_on": occurred if state == "done" else None,
              "planned_at": planned if state == "planned" else None,
              "practice": values.get("practice", ""), "note": values.get("note", ""), "batch": values.get("batch", "")}
    if values["key"].startswith("manual:"):
        fields["title"] = values.get("title", existing.title if existing else "").strip()
        if not fields["title"]:
            raise ValidationError({"title": "Enter the documented vaccination name."})
    if existing and values["expected_version"] != existing.version:
        if all(getattr(existing, key) == value for key, value in fields.items()):
            return existing
        raise HealthConflict()
    if not existing and values["expected_version"] != 0:
        raise HealthConflict()
    row = existing or ChildHealthRecord(baby=baby, key=values["key"], kind=rule["kind"] if rule else "vaccination",
                                        title=rule["title"] if rule else values.get("title", ""),
                                        reference=rule["reference"] if rule else {})
    if not row.title.strip():
        raise ValidationError({"title": "Enter the documented vaccination name."})
    for key, value in fields.items():
        setattr(row, key, value)
    row.updated_by = user
    if existing:
        row.version += 1
    if state == "planned":
        token = _private_event_token(baby, row.key.removeprefix("exam:"))
        event, _ = FamilyEvent.objects.get_or_create(family=baby.family, external_id=token, defaults={
            "type": "family.appointment", "title": "Vorsorgetermin" if baby.family.locale.startswith("de") else "Check-up",
            "starts_at": planned, "actionable": True,
            "payload": {"private_context": True},
        })
        event.starts_at = planned
        event.payload = {"private_context": True, "deep_link": f"/?page=baby&event={event.id}&view=health"}
        event.save(update_fields=["starts_at", "payload", "updated_at"])
        row.event = event
        if rule and not PediatricPreventiveEventReference.objects.filter(event=event).exists():
            provenance = {**rule, "key": rule["rule_key"]}
            PediatricPreventiveEventReference.objects.create(event=event, **_provenance_defaults(baby, provenance))
    row.save()
    return row
