import math
from datetime import datetime, timedelta

from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError
from pygrowthstandards import functional as growth

from .family_modules import care_access
from .models import BabyGrowthMeasurement, BabyGrowthReferenceSetting, BabyProfile


REFERENCE_METADATA = {
    "who_2006": {
        "label": "WHO Child Growth Standards",
        "version": "2006",
        "source_url": "https://www.who.int/tools/child-growth-standards/standards",
    },
    "who_2006_corrected": {
        "label": "WHO Child Growth Standards (corrected age)",
        "version": "2006",
        "source_url": "https://www.who.int/tools/child-growth-standards/standards",
    },
    "intergrowth_21_postnatal": {
        "label": "INTERGROWTH-21st Postnatal Growth Standards for Preterm Infants",
        "version": "INTERGROWTH-21st",
        "source_url": "https://intergrowth21.tghn.org/standards-tools/",
    },
}


def _baby_for_user(user, baby_id):
    baby = BabyProfile.objects.select_related("family").filter(pk=baby_id, active=True).first()
    if not baby:
        raise ValidationError({"baby": "Baby profile not found."})
    _, access = care_access(user, baby.family, "growth")
    if not access.can_view_growth_development:
        raise PermissionDenied("Growth access is not permitted.")
    return baby


def chronological_age_days(baby, measured_at):
    measured_date = measured_at.date() if isinstance(measured_at, datetime) else measured_at
    return max(0, (measured_date - baby.birth_date).days)


def gestational_age_days(baby):
    if baby.gestational_age_weeks is None:
        return None
    return int(baby.gestational_age_weeks) * 7 + int(baby.gestational_age_days or 0)


def corrected_age_days(baby, measured_at):
    chronological = chronological_age_days(baby, measured_at)
    ga = gestational_age_days(baby)
    if ga is None or ga >= 280:
        return chronological
    correction = 280 - ga
    return max(0, chronological - correction)


def set_reference(user, baby_id, *, reference_key, corrected_age_enabled=None):
    baby = _baby_for_user(user, baby_id)
    if reference_key not in REFERENCE_METADATA:
        raise ValidationError({"reference_key": "Unsupported growth reference."})
    setting, _ = BabyGrowthReferenceSetting.objects.get_or_create(baby=baby)
    setting.reference_key = reference_key
    setting.reference_version = f"{REFERENCE_METADATA[reference_key]['label']} {REFERENCE_METADATA[reference_key]['version']}"
    if corrected_age_enabled is not None:
        setting.corrected_age_enabled = bool(corrected_age_enabled)
    setting.save()
    return setting


def add_measurement(user, baby_id, *, measured_at, weight_g=None, length_cm=None, head_circumference_cm=None, source="home", note=""):
    baby = _baby_for_user(user, baby_id)
    if weight_g is None and length_cm is None and head_circumference_cm is None:
        raise ValidationError("Enter at least one growth measurement.")
    now = timezone.now()
    if measured_at > now + timedelta(minutes=5):
        raise ValidationError({"measured_at": "Measurement cannot be in the future."})
    if weight_g is not None and not 300 <= int(weight_g) <= 60000:
        raise ValidationError({"weight_g": "Weight must be between 300 g and 60,000 g."})
    if length_cm is not None and not 20 <= float(length_cm) <= 160:
        raise ValidationError({"length_cm": "Length must be between 20 cm and 160 cm."})
    if head_circumference_cm is not None and not 20 <= float(head_circumference_cm) <= 80:
        raise ValidationError({"head_circumference_cm": "Head circumference must be between 20 cm and 80 cm."})
    if source not in BabyGrowthMeasurement.Source.values:
        raise ValidationError({"source": "Unknown measurement source."})
    return BabyGrowthMeasurement.objects.create(
        family=baby.family,
        baby=baby,
        measured_at=measured_at,
        weight_g=weight_g,
        length_cm=length_cm,
        head_circumference_cm=head_circumference_cm,
        source=source,
        note=str(note or "")[:2000],
        created_by=user,
    )


def _percentile(z):
    if z is None:
        return None
    return round(100 * 0.5 * (1 + math.erf(float(z) / math.sqrt(2))), 1)


def _metric_zscore(baby, measurement, metric, value, setting):
    if value is None:
        return None
    sex = {BabyProfile.ReferenceSex.FEMALE: "F", BabyProfile.ReferenceSex.MALE: "M"}.get(baby.growth_reference_sex)
    if not sex:
        return None
    age_days = chronological_age_days(baby, measurement.measured_at)
    ga_days = gestational_age_days(baby)
    numeric = float(value) / 1000 if metric == "weight" else float(value)
    try:
        if setting.reference_key == "intergrowth_21_postnatal":
            if ga_days is None:
                return None
            pma = ga_days + age_days
            if age_days == 0:
                return growth.zscore(metric, numeric, sex, gestational_age=ga_days)
            if pma > 64 * 7:
                return None
            return growth.zscore(metric, numeric, sex, x_var_type="post_menstrual_age", x_value=pma)
        score_age = corrected_age_days(baby, measurement.measured_at) if setting.corrected_age_enabled or setting.reference_key == "who_2006_corrected" else age_days
        return growth.zscore(metric, numeric, sex, age_days=score_age)
    except (ValueError, KeyError):
        return None


def growth_payload(user, baby_id):
    baby = _baby_for_user(user, baby_id)
    setting, _ = BabyGrowthReferenceSetting.objects.get_or_create(
        baby=baby,
        defaults={
            "reference_key": "who_2006_corrected" if baby.gestational_age_weeks is not None and baby.gestational_age_weeks < 37 else "who_2006",
            "reference_version": "WHO Child Growth Standards 2006",
            "corrected_age_enabled": bool(baby.gestational_age_weeks is not None and baby.gestational_age_weeks < 37),
        },
    )
    metadata = REFERENCE_METADATA.get(setting.reference_key, REFERENCE_METADATA["who_2006"])
    points = []
    for row in baby.growth_measurements.order_by("measured_at", "created_at"):
        metrics = {}
        for metric, field in (("weight", "weight_g"), ("stature", "length_cm"), ("head_circumference", "head_circumference_cm")):
            value = getattr(row, field)
            z = _metric_zscore(baby, row, metric, value, setting)
            metrics[field] = {
                "value": float(value) if value is not None else None,
                "z_score": round(float(z), 3) if z is not None else None,
                "percentile": _percentile(z),
            }
        points.append({
            "id": str(row.id),
            "measured_at": row.measured_at.isoformat(),
            "source": row.source,
            "note": row.note,
            "chronological_age_days": chronological_age_days(baby, row.measured_at),
            "corrected_age_days": corrected_age_days(baby, row.measured_at),
            "metrics": metrics,
        })
    return {
        "baby": str(baby.id),
        "reference": {"key": setting.reference_key, "version": setting.reference_version, **metadata},
        "reference_sex": baby.growth_reference_sex,
        "corrected_age_enabled": setting.corrected_age_enabled,
        "points": points,
        "interpretation": "Percentiles and z-scores describe position within the selected reference population; they are not a diagnosis.",
    }
