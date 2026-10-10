from datetime import datetime, time, timedelta

from django.db import IntegrityError, transaction
from django.db.models import F, Q
from django.utils import timezone

from baby.models import FamilyModuleSetting
from family.push import send_user_push

from .models import PetCareAccess, PetHealthEvent, PetMedication, PetMedicationDose, PetReminderDelivery
from .permissions import MODULE_KEY
from .services import family_zone


def _push_once(access, pet, topic_key, scheduled_for, title, body):
    if scheduled_for > timezone.now():
        return False
    try:
        with transaction.atomic():
            delivery, created = PetReminderDelivery.objects.get_or_create(
                family=pet.family,
                pet=pet,
                membership=access.membership,
                topic_key=topic_key[:180],
                scheduled_for=scheduled_for,
            )
    except IntegrityError:
        return False
    if not created or delivery.sent_at:
        return False
    send_user_push(
        access.membership.user,
        title,
        body,
        f"/?page=pets&pet={pet.id}",
        tag=f"fam-uh-le:pet:{topic_key}"[:180],
    )
    delivery.sent_at = timezone.now()
    delivery.save(update_fields=["sent_at", "updated_at"])
    return True


def _medication_schedules(access, now):
    if not access.remind_medications:
        return 0
    zone = family_zone(access.family)
    local_now = now.astimezone(zone)
    sent = 0
    medications = PetMedication.objects.filter(
        family=access.family,
        pet__active=True,
        active=True,
        starts_at__lte=now,
    ).filter(Q(ends_at__isnull=True) | Q(ends_at__gte=now)).select_related("pet")
    for medication in medications:
        times = medication.schedule.get("times", []) if isinstance(medication.schedule, dict) else []
        for clock in times:
            try:
                hour, minute = [int(part) for part in str(clock).split(":", 1)]
                scheduled_local = datetime.combine(local_now.date(), time(hour, minute), tzinfo=zone)
            except (TypeError, ValueError):
                continue
            scheduled_for = scheduled_local.astimezone(timezone.get_current_timezone())
            if scheduled_for > now or now - scheduled_for > timedelta(hours=6):
                continue
            already_handled = PetMedicationDose.objects.filter(
                medication=medication,
                scheduled_for__date=scheduled_for.date(),
                state__in=[PetMedicationDose.State.GIVEN, PetMedicationDose.State.SKIPPED, PetMedicationDose.State.CANCELED],
            ).exists()
            if already_handled:
                continue
            sent += int(_push_once(
                access,
                medication.pet,
                f"med:{medication.id}:{clock}",
                scheduled_for,
                f"{medication.pet.name}: Medikament",
                f"{medication.name} · {medication.instruction_text}".strip(" ·"),
            ))
    return sent


def _prevention_schedules(access, now):
    if not access.remind_prevention:
        return 0
    zone = family_zone(access.family)
    sent = 0
    events = PetHealthEvent.objects.filter(
        family=access.family,
        pet__active=True,
        next_due_at__isnull=False,
        next_due_at__gte=now - timedelta(days=1),
        next_due_at__lte=now + timedelta(days=8),
    ).exclude(occurred_at__gte=F("next_due_at")).select_related("pet")
    for event in events:
        lead = timedelta(days=1) if event.kind == PetHealthEvent.Kind.VET else timedelta(days=7)
        due_local = event.next_due_at.astimezone(zone)
        reminder_date = (due_local - lead).date()
        scheduled_local = datetime.combine(reminder_date, time(9, 0), tzinfo=zone)
        scheduled_for = scheduled_local.astimezone(timezone.get_current_timezone())
        if scheduled_for > now or now - scheduled_for > timedelta(days=1):
            continue
        sent += int(_push_once(
            access,
            event.pet,
            f"health:{event.id}",
            scheduled_for,
            f"{event.pet.name}: {event.title}",
            f"Fällig {due_local.strftime('%d.%m.%Y %H:%M')}" if event.kind == PetHealthEvent.Kind.VET else f"Fällig am {due_local.strftime('%d.%m.%Y')}",
        ))
    return sent


def process_pet_reminders(now=None):
    now = now or timezone.now()
    enabled_family_ids = FamilyModuleSetting.objects.filter(module_key=MODULE_KEY, enabled=True).values_list("family_id", flat=True)
    accesses = PetCareAccess.objects.filter(
        family_id__in=enabled_family_ids,
        can_care=True,
        membership__family__status="active",
    ).select_related("family", "membership__user")
    sent = 0
    for access in accesses:
        sent += _medication_schedules(access, now)
        sent += _prevention_schedules(access, now)
    return sent
