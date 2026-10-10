import hashlib
import hmac
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from family.models import FamilyEvent, Membership, ShoppingItem, ShoppingList, Task, TaskList, UserProfile

from .family_modules import care_access, require_manager, require_module
from .models import BabyGrowthReferenceSetting, BabyProfile, CareCircleAccess, ManagedChildGuardian, PregnancyBaby, PregnancyJournalEntry, PregnancyJourney


User = get_user_model()


def local_date(family, value=None):
    value = value or timezone.now()
    return value.astimezone(ZoneInfo(family.timezone)).date()


def pregnancy_progress(pregnancy, on_date=None):
    on_date = on_date or local_date(pregnancy.family)
    start = pregnancy.start_date or pregnancy.expected_due_date - timedelta(days=280)
    elapsed = (on_date - start).days
    week = max(0, elapsed // 7)
    day = max(0, elapsed % 7)
    remaining = (pregnancy.expected_due_date - on_date).days
    return {
        "week": week,
        "day": day,
        "days_until_due": remaining,
        "due_date": pregnancy.expected_due_date.isoformat(),
        "is_overdue": remaining < 0,
    }


def create_pregnancy(user, family, *, expected_due_date, baby_count=1, estimated_from="manual", start_date=None, notes="", weekly_notification_enabled=False):
    require_module(family)
    require_manager(user, family)
    try:
        count = int(baby_count)
    except (TypeError, ValueError):
        raise ValidationError({"baby_count": "Use a whole number between 1 and 3."})
    if count not in (1, 2, 3):
        raise ValidationError({"baby_count": "Pregnancy supports one to three expected babies."})
    if PregnancyJourney.objects.filter(family=family, status=PregnancyJourney.Status.ACTIVE).exists():
        raise ValidationError("An active pregnancy journey already exists for this family.")
    journey = PregnancyJourney.objects.create(
        family=family,
        expected_due_date=expected_due_date,
        estimated_from=estimated_from,
        start_date=start_date,
        notes=notes,
        weekly_notification_enabled=weekly_notification_enabled,
        created_by=user,
    )
    for index in range(count):
        PregnancyBaby.objects.create(
            pregnancy=journey,
            stable_label=chr(ord("A") + index),
            display_name=f"Baby {chr(ord('A') + index)}" if count > 1 else "Baby",
            order_index=index,
        )
    return journey


def update_expected_baby(user, expected_baby, *, display_name=None):
    require_manager(user, expected_baby.pregnancy.family)
    require_module(expected_baby.pregnancy.family)
    if display_name is not None:
        expected_baby.display_name = str(display_name).strip()[:80]
        expected_baby.save(update_fields=["display_name", "updated_at"])
    return expected_baby


def _technical_username(family, identity_key):
    base = f"child-{family.id.hex[:8]}-{identity_key.hex[:20]}"
    candidate = base
    suffix = 1
    while User.objects.filter(username=candidate).exists():
        suffix += 1
        candidate = f"{base}-{suffix}"
    return candidate


def _sync_birth_profile(user, membership, *, display_name, birth_date):
    membership.role = Membership.Role.CHILD
    membership.display_name = display_name
    membership.save(update_fields=["role", "display_name", "updated_at"])
    profile, _ = UserProfile.objects.get_or_create(user=membership.user)
    profile.birth_year = birth_date.year
    profile.birth_month = birth_date.month
    profile.birth_day = birth_date.day
    profile.save(update_fields=["birth_year", "birth_month", "birth_day", "updated_at"])
    membership.user.set_unusable_password()
    membership.user.email = ""
    membership.user.save(update_fields=["password", "email"])


def _ensure_guardians(baby):
    guardian_access = CareCircleAccess.objects.filter(family=baby.family, is_guardian=True, membership__role__in=[Membership.Role.OWNER, Membership.Role.ADULT]).select_related("membership")
    for access in guardian_access:
        ManagedChildGuardian.objects.get_or_create(baby=baby, membership=access.membership, defaults={"can_manage_account": True})


@transaction.atomic
def create_managed_child(user, family, *, display_name, birth_date, birth_time=None, gestational_age_weeks=None, gestational_age_days=None, birth_weight_g=None, birth_length_cm=None, birth_head_circumference_cm=None, growth_reference_sex="unspecified", source_pregnancy=None, source_pregnancy_baby=None, client_identity_key=None):
    require_module(family)
    require_manager(user, family)
    if source_pregnancy_baby:
        existing = BabyProfile.objects.select_for_update().filter(source_pregnancy_baby=source_pregnancy_baby).first()
        identity_key = source_pregnancy_baby.id
    elif client_identity_key:
        existing = BabyProfile.objects.select_for_update().filter(client_identity_key=client_identity_key).first()
        identity_key = client_identity_key
    else:
        raise ValidationError({"client_identity_key": "A stable client identity key is required when no pregnancy baby is supplied."})
    if existing:
        return existing
    if source_pregnancy and source_pregnancy.family_id != family.id:
        raise ValidationError("Pregnancy does not belong to this family.")
    if source_pregnancy_baby and source_pregnancy_baby.pregnancy.family_id != family.id:
        raise ValidationError("Expected baby does not belong to this family.")
    if gestational_age_weeks is not None and not 20 <= int(gestational_age_weeks) <= 44:
        raise ValidationError({"gestational_age_weeks": "Use a gestational age between 20 and 44 weeks."})
    if gestational_age_days is not None and not 0 <= int(gestational_age_days) <= 6:
        raise ValidationError({"gestational_age_days": "Use days 0 through 6."})
    child_user = User(username=_technical_username(family, identity_key), email="", is_active=True)
    child_user.set_unusable_password()
    child_user.save()
    membership = Membership.objects.create(
        family=family,
        user=child_user,
        role=Membership.Role.CHILD,
        display_name=str(display_name).strip()[:80] or "Baby",
        birthday_visibility=Membership.BirthdayVisibility.FULL_DATE,
    )
    UserProfile.objects.create(
        user=child_user,
        birth_year=birth_date.year,
        birth_month=birth_date.month,
        birth_day=birth_date.day,
    )
    baby = BabyProfile.objects.create(
        family=family,
        membership=membership,
        source_pregnancy=source_pregnancy,
        source_pregnancy_baby=source_pregnancy_baby,
        client_identity_key=None if source_pregnancy_baby else client_identity_key,
        display_name=membership.display_name,
        birth_date=birth_date,
        birth_time=birth_time,
        gestational_age_weeks=gestational_age_weeks,
        gestational_age_days=gestational_age_days,
        birth_weight_g=birth_weight_g,
        birth_length_cm=birth_length_cm,
        birth_head_circumference_cm=birth_head_circumference_cm,
        growth_reference_sex=growth_reference_sex,
        created_by=user,
    )
    corrected = bool(gestational_age_weeks is not None and int(gestational_age_weeks) < 37)
    BabyGrowthReferenceSetting.objects.create(baby=baby, corrected_age_enabled=corrected)
    _ensure_guardians(baby)
    if source_pregnancy_baby:
        source_pregnancy_baby.status = PregnancyBaby.Status.BORN
        if not source_pregnancy_baby.display_name or source_pregnancy_baby.display_name.startswith("Baby"):
            source_pregnancy_baby.display_name = baby.display_name
        source_pregnancy_baby.save(update_fields=["status", "display_name", "updated_at"])
    return baby


@transaction.atomic
def complete_birth(user, pregnancy, babies):
    require_module(pregnancy.family)
    require_manager(user, pregnancy.family)
    pregnancy = PregnancyJourney.objects.select_for_update().get(pk=pregnancy.pk)
    expected = list(pregnancy.expected_babies.select_for_update().order_by("order_index"))
    supplied = {str(row.get("pregnancy_baby")): row for row in babies or []}
    if set(supplied) != {str(row.id) for row in expected}:
        raise ValidationError({"babies": "Birth transition requires one payload for every expected baby."})
    result = []
    for expected_baby in expected:
        row = supplied[str(expected_baby.id)]
        result.append(create_managed_child(
            user,
            pregnancy.family,
            display_name=row.get("display_name") or expected_baby.display_name or expected_baby.stable_label,
            birth_date=row.get("birth_date"),
            birth_time=row.get("birth_time"),
            gestational_age_weeks=row.get("gestational_age_weeks"),
            gestational_age_days=row.get("gestational_age_days"),
            birth_weight_g=row.get("birth_weight_g"),
            birth_length_cm=row.get("birth_length_cm"),
            birth_head_circumference_cm=row.get("birth_head_circumference_cm"),
            growth_reference_sex=row.get("growth_reference_sex", "unspecified"),
            source_pregnancy=pregnancy,
            source_pregnancy_baby=expected_baby,
        ))
    pregnancy.status = PregnancyJourney.Status.BIRTH_COMPLETED
    pregnancy.weekly_notification_enabled = False
    pregnancy.save(update_fields=["status", "weekly_notification_enabled", "updated_at"])
    return result


def archive_pregnancy(user, pregnancy, *, status="archived"):
    require_manager(user, pregnancy.family)
    if status not in {PregnancyJourney.Status.ARCHIVED, PregnancyJourney.Status.ENDED}:
        raise ValidationError({"status": "Use archived or ended."})
    pregnancy.status = status
    pregnancy.weekly_notification_enabled = False
    pregnancy.save(update_fields=["status", "weekly_notification_enabled", "updated_at"])
    return pregnancy


def pregnancy_template_items(user, pregnancy, *, include_tasks=True, include_shopping=True):
    require_module(pregnancy.family)
    care_access(user, pregnancy.family, "pregnancy")
    created = {"tasks": [], "shopping_items": []}
    if include_tasks:
        task_list, _ = TaskList.objects.get_or_create(family=pregnancy.family, name="Baby-Vorbereitung", defaults={"icon": "sparkles"})
        templates = [
            ("Klinik-/Geburtstasche vorbereiten", 35),
            ("Kinderarzt / U-Termine vorbereiten", 37),
            ("Schlafplatz und Wickelbereich prüfen", 36),
        ]
        for title, week in templates:
            due = pregnancy.expected_due_date - timedelta(weeks=max(0, 40 - week))
            due_at = datetime.combine(due, time(hour=9), tzinfo=ZoneInfo(pregnancy.family.timezone))
            task, _ = Task.objects.get_or_create(
                family=pregnancy.family,
                task_list=task_list,
                title=title,
                source=f"pregnancy:{pregnancy.id}",
                defaults={"due_at": due_at, "created_by": user, "tags": ["baby", "pregnancy"]},
            )
            created["tasks"].append(task.id)
    if include_shopping:
        shopping_list = ShoppingList.objects.filter(family=pregnancy.family, archived=False).order_by("sort_order", "created_at").first()
        if shopping_list:
            for name, category in [("Windeln", "Baby"), ("Feuchttücher / Waschlappen", "Baby"), ("Spucktücher", "Baby")]:
                item, _ = ShoppingItem.objects.get_or_create(shopping_list=shopping_list, name=name, defaults={"category": category, "added_by": user})
                created["shopping_items"].append(item.id)
    return created


def _private_prenatal_token(pregnancy, starts_at, event_type):
    raw = f"pregnancy-event:{pregnancy.id}:{event_type}:{starts_at.isoformat()}".encode()
    digest = hmac.new(settings.SECRET_KEY.encode(), raw, hashlib.sha256).hexdigest()[:32]
    return f"familyos-private:{digest}"


def prenatal_calendar_event(user, pregnancy, *, title, starts_at, ends_at=None, event_type="baby.prenatal", payload=None):
    require_module(pregnancy.family)
    care_access(user, pregnancy.family, "pregnancy")
    private_note = str((payload or {}).get("note") or "").strip()
    private_title = str(title or "").strip()
    if private_title or private_note:
        note = private_title
        if private_note:
            note = f"{note}\n{private_note}" if note else private_note
        PregnancyJournalEntry.objects.create(
            pregnancy=pregnancy,
            entry_date=starts_at.astimezone(ZoneInfo(pregnancy.family.timezone)).date(),
            note=note[:12000],
            created_by=user,
        )
    return FamilyEvent.objects.create(
        family=pregnancy.family,
        type="family.appointment",
        title="Termin" if pregnancy.family.locale.startswith("de") else "Appointment",
        starts_at=starts_at,
        ends_at=ends_at,
        actionable=True,
        payload={"deep_link": "/?page=baby&view=pregnancy", "private_context": True},
        external_id=_private_prenatal_token(pregnancy, starts_at, event_type),
    )
