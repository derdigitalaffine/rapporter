from datetime import timedelta

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import APIException, ValidationError

from family.models import FamilyEvent, Task, TaskList
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
    event = row.event if row.event_id else None
    planned = event.starts_at if event and row.state == "planned" else row.planned_at
    return {"key": row.key, "kind": row.kind, "title": row.title, "state": row.state,
            "occurred_on": row.occurred_on.isoformat() if row.occurred_on else None,
            "planned_at": planned.isoformat() if planned else None,
            "event_starts_at": event.starts_at.isoformat() if event else None,
            "practice": row.practice, "note": row.note, "batch": row.batch,
            "reference": row.reference, "event": str(row.event_id) if row.event_id else None, "version": row.version,
            "reminder": {"task": str(row.reminder_task_id), "due_at": row.reminder_task.due_at.isoformat() if row.reminder_task.due_at else None,
                         "completed": bool(row.reminder_task.completed_at)} if row.reminder_task_id else None}


def reference_rule(reference):
    kind = "vaccination" if ":" in reference.rule_key else "exam"
    return {"key": f"{kind}:{reference.rule_key}", "rule_key": reference.rule_key, "kind": kind,
            "title": reference.rule_key, "start_day": reference.start_day, "end_day": reference.end_day,
            "target_day": reference.target_day, "reference": {
                "package_id": str(reference.reference_package_id) if reference.reference_package_id else None,
                "source_key": reference.source_key, "source_version": reference.source_version,
                "checksum": reference.source_checksum, "locale": reference.locale}}


def health_payload(user, baby, language="de"):
    child_scope_access(user, baby, "development")
    rules, package = health_rules(baby, language)
    records = {row.key: row for row in baby.health_records.select_related("event", "reminder_task")}
    references = {reference_rule(row)["key"]: row for row in baby.preventive_event_references.select_related("event")}
    current_keys = {row["key"] for row in rules}
    rules.extend(reference_rule(row) for key, row in references.items() if key not in current_keys and key not in records)
    age_days = (local_date(baby.family) - baby.birth_date).days
    items = []
    for rule in rules:
        record = records.pop(rule["key"], None)
        reference = references.get(rule["key"])
        projection = {}
        if reference:
            rule = {**rule, **reference_rule(reference), "title": rule["title"]}
        if reference and not record:
            projection = {"state": "planned", "planned_at": reference.event.starts_at.isoformat(),
                          "event_starts_at": reference.event.starts_at.isoformat(), "event": str(reference.event_id)}
        items.append({**rule, "historical": rule["end_day"] < age_days,
                      "window_start": (baby.birth_date + timedelta(days=rule["start_day"])).isoformat(),
                      "window_end": (baby.birth_date + timedelta(days=rule["end_day"])).isoformat(),
                      "state": "unknown", "version": 0, **(serialize_record(record) if record else projection)})
    items.extend({**serialize_record(row), "historical": True} for row in records.values())
    return {"baby": str(baby.id), "items": items,
            "vaccination_reference_available": bool(package and package.payload.get("vaccinations")),
            "vaccination_reference": {
                "title": package.source_title, "version": package.source_version,
                "published_on": package.published_at.date().isoformat() if package.published_at else None,
                "effective_from": package.effective_from.isoformat() if package.effective_from else None,
                "checksum": package.checksum,
            } if package and package.payload.get("vaccinations") else None,
            "notice": "Recorded history and published references, not diagnosis or individual medical advice."}


@transaction.atomic
def create_health_reminders(user, baby, entries, remind_at):
    # The private association is child-scoped. The shared Task deliberately
    # contains no child identity, medical title, reference or health deep link.
    baby = BabyProfile.objects.select_for_update(of=("self",)).select_related("family", "membership").get(pk=baby.id, active=True)
    child_scope_access(user, baby, "development")
    if remind_at <= timezone.now():
        raise ValidationError({"remind_at": "Choose a future reminder date and time."})
    rules, _ = health_rules(baby)
    rules = {row["key"]: row for row in rules if row["kind"] == "vaccination"}
    records = {row.key: row for row in baby.health_records.select_related("reminder_task").select_for_update(of=("self",))}
    selected = [records.get(entry["key"]) for entry in entries]
    if all(row and row.reminder_task_id for row in selected):
        task_ids = {row.reminder_task_id for row in selected}
        if len(task_ids) == 1 and all(row.reminder_task.due_at == remind_at for row in selected):
            return selected
    age = (local_date(baby.family) - baby.birth_date).days
    for entry, row in zip(entries, selected):
        rule = rules.get(entry["key"])
        if not rule or rule["end_day"] < age or row and row.state in {"done", "planned"}:
            raise ValidationError({"entries": "Choose open current or future vaccination references."})
        if entry["reference_checksum"] != rule["reference"]["checksum"] or entry["expected_version"] != (row.version if row else 0):
            raise HealthConflict()
        if row and row.reminder_task_id:
            raise HealthConflict("A reminder task already exists. Manage it in Tasks.")
    task_list, _ = TaskList.objects.get_or_create(family=baby.family, name="Allgemein", defaults={"icon": "list-check"})
    task = Task.objects.create(family=baby.family, task_list=task_list, created_by=user, assignee=user,
                              title="Termin vereinbaren" if baby.family.locale.startswith("de") else "Arrange appointment",
                              due_at=remind_at, source="manual")
    result = []
    for entry, row in zip(entries, selected):
        rule = rules[entry["key"]]
        row = row or ChildHealthRecord(baby=baby, key=rule["key"], kind="vaccination", title=rule["title"], reference=rule["reference"])
        if row.pk and entry["expected_version"]:
            row.version += 1
        row.reminder_task = task
        row.updated_by = user
        row.save()
        result.append(row)
    return result


@transaction.atomic
def save_health_record(user, baby, values):
    # Serialize competing create/update requests for the same child and key.
    baby = BabyProfile.objects.select_for_update(of=("self",)).select_related("family", "membership").get(pk=baby.id, active=True)
    child_scope_access(user, baby, "development")
    rules, _ = health_rules(baby)
    rule = next((row for row in rules if row["key"] == values["key"]), None)
    existing = ChildHealthRecord.objects.filter(baby=baby, key=values["key"]).first()
    token = _private_event_token(baby, values["key"].removeprefix("exam:"))
    events = FamilyEvent.objects.select_for_update().filter(family=baby.family)
    linked = events.filter(pk=existing.event_id).first() if existing and existing.event_id else events.filter(external_id=token).first()
    provenance = PediatricPreventiveEventReference.objects.filter(baby=baby,event=linked).first() if linked else None
    if provenance:
        rule = {**(rule or {}), **reference_rule(provenance), "title": rule["title"] if rule else provenance.rule_key}
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
    if state == "planned" and not linked and planned < timezone.now():
        raise ValidationError({"planned_at": "Past history must not create a new appointment."})
    fields = {"state": state, "occurred_on": occurred if state == "done" else None,
              "planned_at": planned if state == "planned" else None,
              "practice": values.get("practice", ""), "note": values.get("note", ""), "batch": values.get("batch", "")}
    if values["key"].startswith("manual:"):
        fields["title"] = values.get("title", existing.title if existing else "").strip()
        if not fields["title"]:
            raise ValidationError({"title": "Enter the documented vaccination name."})
    if existing and values["expected_version"] != existing.version:
        if all(getattr(existing, key) == value for key, value in fields.items()) and (state != "planned" or not linked or linked.starts_at == planned):
            return existing
        raise HealthConflict()
    if not existing and values["expected_version"] != 0:
        raise HealthConflict()
    if state == "planned" and linked and values.get("event_starts_at") != linked.starts_at:
        raise HealthConflict("The calendar appointment changed. Reload before saving.")
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
        event = linked
        if not event:
            event, created = FamilyEvent.objects.get_or_create(family=baby.family, external_id=token, defaults={
                "type":"family.appointment", "title":"Vorsorgetermin" if baby.family.locale.startswith("de") else "Check-up",
                "starts_at":planned, "actionable":True, "payload":{"private_context":True}})
            if not created:
                event = events.get(pk=event.pk)
                if values.get("event_starts_at") != event.starts_at:
                    raise HealthConflict("The calendar appointment changed. Reload before saving.")
        event.starts_at = planned
        event.payload = {**event.payload, "private_context": True, "deep_link": f"/?page=baby&event={event.id}&view=health"}
        event.save(update_fields=["starts_at", "payload", "updated_at"])
        row.event = event
        if rule and not PediatricPreventiveEventReference.objects.filter(event=event).exists():
            provenance = {**rule, "key": rule["rule_key"]}
            PediatricPreventiveEventReference.objects.create(event=event, **_provenance_defaults(baby, provenance))
    row.save()
    return row
