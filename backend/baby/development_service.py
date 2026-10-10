from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from family.models import FamilyEvent

from .family_modules import care_access
from .growth_service import corrected_age_days, chronological_age_days
from .models import AppointmentQuestion, BabyProfile, DevelopmentObservation, DevelopmentReference


CDC_SOURCE_KEY = "cdc_act_early"
CDC_SOURCE_VERSION = "2026-02-16"
CDC_SOURCE_URL = "https://www.cdc.gov/act-early/milestones/"

# Paraphrased, non-diagnostic prompts. The source/version is retained separately.
REFERENCE_ROWS = [
    (2, "social", "looks-at-face", "Schaut Gesichter aufmerksam an", "Looks at faces with interest"),
    (2, "language", "sounds-other-than-crying", "Macht erste Laute außer Weinen", "Makes sounds other than crying"),
    (2, "movement", "head-up-tummy", "Hebt in Bauchlage kurz den Kopf", "Lifts head briefly during tummy time"),
    (4, "social", "smiles-for-attention", "Lächelt, um Kontakt aufzunehmen", "Smiles to engage with people"),
    (4, "language", "coos-back", "Antwortet auf Ansprache mit Lauten", "Responds to voices with sounds"),
    (4, "movement", "holds-head-steady", "Hält den Kopf zunehmend stabil", "Holds head increasingly steady"),
    (6, "social", "knows-familiar-people", "Reagiert vertraut auf bekannte Personen", "Responds familiarly to known people"),
    (6, "language", "takes-turns-sounds", "Wechselt sich beim Lautgeben ab", "Takes turns making sounds"),
    (6, "movement", "rolls-tummy-back", "Rollt sich aus der Bauchlage", "Rolls from tummy position"),
    (9, "social", "reacts-to-leaving", "Reagiert, wenn Bezugspersonen weggehen", "Reacts when caregivers leave"),
    (9, "cognitive", "looks-for-dropped", "Sucht nach heruntergefallenen Dingen", "Looks for dropped objects"),
    (9, "movement", "sits-without-support", "Sitzt zeitweise ohne Unterstützung", "Sits for a while without support"),
    (12, "social", "plays-simple-games", "Spielt einfache soziale Spiele mit", "Joins simple social games"),
    (12, "language", "waves-or-gesture", "Nutzt einfache Gesten wie Winken", "Uses simple gestures such as waving"),
    (12, "movement", "pulls-to-stand", "Zieht sich zum Stehen hoch", "Pulls up to stand"),
    (15, "language", "tries-words", "Probiert erste verständliche Wörter", "Tries first recognizable words"),
    (15, "cognitive", "uses-object-right", "Nutzt vertraute Dinge passend", "Uses familiar objects appropriately"),
    (15, "movement", "few-steps", "Macht einige Schritte selbstständig", "Takes a few independent steps"),
    (18, "social", "moves-away-checks-back", "Entfernt sich kurz und sucht Blickkontakt zurück", "Moves away briefly and checks back"),
    (18, "language", "several-words", "Verwendet mehrere Wörter mit Bedeutung", "Uses several meaningful words"),
    (18, "movement", "walks-alone", "Läuft selbstständig", "Walks independently"),
    (24, "social", "notices-upset", "Bemerkt Gefühle anderer und reagiert", "Notices and responds to others' emotions"),
    (24, "language", "two-word-combinations", "Verbindet Wörter zu kurzen Aussagen", "Combines words into short phrases"),
    (24, "cognitive", "uses-switches-knobs", "Probiert einfache Schalter oder Drehknöpfe aus", "Explores simple switches or knobs"),
]

# Mid-points inside the G-BA examination periods, used only as planning suggestions.
U_EXAMS = [
    ("U2", 6, "3.–10. Lebenstag"),
    ("U3", 31, "4.–5. Lebenswoche"),
    ("U4", 105, "3.–4. Lebensmonat"),
    ("U5", 198, "6.–7. Lebensmonat"),
    ("U6", 335, "10.–12. Lebensmonat"),
    ("U7", 685, "21.–24. Lebensmonat"),
    ("U7a", 1065, "34.–36. Lebensmonat"),
    ("U8", 1430, "46.–48. Lebensmonat"),
    ("U9", 1887, "60.–64. Lebensmonat"),
]
GBA_SOURCE_URL = "https://www.g-ba.de/richtlinien/15/"


def _baby_for_user(user, baby_id):
    baby = BabyProfile.objects.select_related("family").filter(pk=baby_id, active=True).first()
    if not baby:
        raise ValidationError({"baby": "Baby profile not found."})
    _, access = care_access(user, baby.family, "development")
    if not access.can_view_growth_development:
        raise PermissionDenied("Development access is not permitted.")
    return baby


def ensure_references():
    for age, category, key, de, en in REFERENCE_ROWS:
        DevelopmentReference.objects.get_or_create(
            source_key=CDC_SOURCE_KEY,
            source_version=CDC_SOURCE_VERSION,
            milestone_key=key,
            defaults={
                "age_month_start": age,
                "age_month_end": age,
                "category": category,
                "localized_text": {"de": de, "en": en},
                "source_url": CDC_SOURCE_URL,
            },
        )


def effective_age_days(baby, on_date=None):
    on_date = on_date or timezone.localdate()
    chronological = chronological_age_days(baby, on_date)
    if baby.gestational_age_weeks is not None and (40 * 7 - (baby.gestational_age_weeks * 7 + (baby.gestational_age_days or 0))) > 21:
        return corrected_age_days(baby, on_date)
    return chronological


def development_payload(user, baby_id, *, language="de"):
    baby = _baby_for_user(user, baby_id)
    ensure_references()
    age_days = effective_age_days(baby)
    age_months = max(0, int(age_days / 30.4375))
    checkpoints = [2, 4, 6, 9, 12, 15, 18, 24]
    checkpoint = next((age for age in checkpoints if age >= age_months), checkpoints[-1])
    if age_months < checkpoints[0]:
        checkpoint = checkpoints[0]
    refs = list(DevelopmentReference.objects.filter(source_key=CDC_SOURCE_KEY, source_version=CDC_SOURCE_VERSION, age_month_start=checkpoint))
    observations = {row.milestone_key: row for row in DevelopmentObservation.objects.filter(baby=baby, milestone_key__in=[r.milestone_key for r in refs])}
    return {
        "baby": str(baby.id),
        "age_days": chronological_age_days(baby, timezone.localdate()),
        "effective_age_days": age_days,
        "checklist_age_months": checkpoint,
        "source": {"key": CDC_SOURCE_KEY, "version": CDC_SOURCE_VERSION, "url": CDC_SOURCE_URL},
        "items": [
            {
                "key": ref.milestone_key,
                "category": ref.category,
                "text": ref.localized_text.get(language, ref.localized_text.get("en", ref.milestone_key)),
                "state": observations.get(ref.milestone_key).state if observations.get(ref.milestone_key) else None,
                "observed_at": observations.get(ref.milestone_key).observed_at.isoformat() if observations.get(ref.milestone_key) and observations.get(ref.milestone_key).observed_at else None,
                "note": observations.get(ref.milestone_key).note if observations.get(ref.milestone_key) else "",
            }
            for ref in refs
        ],
        "interpretation": "Milestones are observation prompts, not a score or diagnosis. Discuss questions or concerns with a qualified clinician.",
    }


def record_observation(user, baby_id, *, milestone_key="", title="", state="observed", observed_at=None, note="", media_key=""):
    baby = _baby_for_user(user, baby_id)
    if state not in DevelopmentObservation.State.values:
        raise ValidationError({"state": "Use observed, not_observed or later."})
    if not milestone_key and not title:
        raise ValidationError("Choose a reference milestone or enter a custom observation title.")
    if milestone_key:
        ensure_references()
        if not DevelopmentReference.objects.filter(source_key=CDC_SOURCE_KEY, source_version=CDC_SOURCE_VERSION, milestone_key=milestone_key).exists():
            raise ValidationError({"milestone_key": "Unknown milestone reference."})
    defaults = {
        "family": baby.family,
        "state": state,
        "observed_at": observed_at or (timezone.now() if state == DevelopmentObservation.State.OBSERVED else None),
        "note": str(note or "")[:4000],
        "media_key": str(media_key or "")[:180],
        "created_by": user,
    }
    if milestone_key:
        row, _ = DevelopmentObservation.objects.update_or_create(baby=baby, milestone_key=milestone_key, defaults={**defaults, "title": ""})
        return row
    return DevelopmentObservation.objects.create(baby=baby, milestone_key="", title=str(title).strip()[:160], **defaults)


def ensure_u_exam_events(user, baby_id):
    baby = _baby_for_user(user, baby_id)
    zone = ZoneInfo(baby.family.timezone)
    created = []
    now = timezone.now()
    for name, days, label in U_EXAMS:
        event_date = baby.birth_date + timedelta(days=days)
        starts_at = datetime.combine(event_date, time(hour=9), tzinfo=zone)
        external_id = f"baby:{baby.id}:preventive:{name}"
        event, _ = FamilyEvent.objects.get_or_create(
            family=baby.family,
            external_id=external_id,
            defaults={
                "type": "baby.preventive",
                "title": f"{name} Vorsorge · {baby.display_name}",
                "starts_at": starts_at,
                "actionable": True,
                "payload": {
                    "baby_id": str(baby.id),
                    "exam": name,
                    "recommended_window": label,
                    "source_url": GBA_SOURCE_URL,
                    "planning_suggestion": True,
                },
            },
        )
        if event.starts_at >= now - timedelta(days=30):
            created.append(event)
    return created


def add_appointment_question(user, baby_id, *, event_id, text):
    baby = _baby_for_user(user, baby_id)
    event = FamilyEvent.objects.filter(pk=event_id, family=baby.family, type="baby.preventive").first()
    if not event or str(event.payload.get("baby_id")) != str(baby.id):
        raise ValidationError({"event": "Preventive appointment not found for this baby."})
    value = str(text or "").strip()
    if not value:
        raise ValidationError({"text": "Question cannot be empty."})
    return AppointmentQuestion.objects.create(family=baby.family, baby=baby, event=event, text=value[:2000], created_by=user)
