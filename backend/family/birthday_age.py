from .birthday_age_models import BirthdayAgePreference


def age_preference_map(family):
    return dict(family.birthday_age_preferences.values_list("target_key", "show_age"))


def age_is_enabled(family, target_key):
    row = BirthdayAgePreference.objects.filter(family=family, target_key=target_key).only("show_age").first()
    return True if row is None else row.show_age


def set_age_enabled(family, target_key, value):
    preference, _ = BirthdayAgePreference.objects.update_or_create(
        family=family,
        target_key=target_key,
        defaults={"show_age": bool(value)},
    )
    return preference.show_age
