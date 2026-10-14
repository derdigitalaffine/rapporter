from django.db import migrations


FAMILYOS_PROVIDERS = {"familyos", "fam-uh-le"}


def detach_stale_familyos_sources(apps, schema_editor):
    """Restore app-owned legacy calendar events that still point at an old source.

    Real integration projections carry an external_id and must stay source-owned.
    Historical app-created FamilyOS events predate that contract and can retain a
    stale source foreign key, which makes the modern calendar API treat them as
    external/read-only.
    """
    FamilyEvent = apps.get_model("family", "FamilyEvent")
    queryset = FamilyEvent.objects.filter(
        type="calendar.event",
        source__isnull=False,
        external_id="",
    )
    for event in queryset.iterator():
        payload = event.payload if isinstance(event.payload, dict) else {}
        provider = str(payload.get("provider") or "").strip().lower()
        if provider in FAMILYOS_PROVIDERS:
            event.source_id = None
            event.save(update_fields=["source"])


class Migration(migrations.Migration):
    dependencies = [("family", "0235_userprofile_avatar_appearance")]

    operations = [
        migrations.RunPython(detach_stale_familyos_sources, migrations.RunPython.noop),
    ]
