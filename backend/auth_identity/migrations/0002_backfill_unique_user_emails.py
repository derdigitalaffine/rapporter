from collections import Counter
import unicodedata

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import migrations


def normalize_email(value):
    raw = unicodedata.normalize("NFKC", str(value or "")).strip()
    if not raw or "@" not in raw:
        return ""
    local, domain = raw.rsplit("@", 1)
    normalized = f"{local.casefold()}@{domain.casefold()}"
    try:
        validate_email(normalized)
    except ValidationError:
        return ""
    return normalized


def backfill(apps, schema_editor):
    app_label, model_name = settings.AUTH_USER_MODEL.split(".")
    User = apps.get_model(app_label, model_name)
    EmailIdentity = apps.get_model("auth_identity", "EmailIdentity")

    rows = []
    counts = Counter()
    for user in User.objects.exclude(email="").only("id", "email").iterator():
        normalized = normalize_email(user.email)
        if not normalized:
            continue
        rows.append((user.pk, normalized))
        counts[normalized] += 1

    for user_id, normalized in rows:
        if counts[normalized] != 1:
            continue
        EmailIdentity.objects.get_or_create(
            user_id=user_id,
            kind="primary",
            defaults={
                "email": normalized,
                "email_normalized": normalized,
            },
        )
        User.objects.filter(pk=user_id).update(email=normalized)


class Migration(migrations.Migration):
    dependencies = [
        ("auth_identity", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(backfill, migrations.RunPython.noop),
    ]
