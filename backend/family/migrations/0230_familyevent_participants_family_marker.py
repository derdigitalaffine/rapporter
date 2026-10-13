from django.db import migrations, models


def migrate_legacy_member_assignments(apps, schema_editor):
    FamilyEvent = apps.get_model("family", "FamilyEvent")
    Membership = apps.get_model("family", "Membership")
    for event in FamilyEvent.objects.all().iterator():
        payload = event.payload if isinstance(event.payload, dict) else {}
        member_id = payload.get("member_id")
        if not member_id:
            continue
        member = Membership.objects.filter(pk=member_id, family_id=event.family_id).first()
        if member:
            event.participants.add(member)


class Migration(migrations.Migration):
    dependencies = [
        ("family", "0229_membership_calendar_color"),
    ]

    operations = [
        migrations.AddField(
            model_name="familyevent",
            name="participants",
            field=models.ManyToManyField(blank=True, related_name="calendar_events", to="family.membership"),
        ),
        migrations.AddField(
            model_name="familyevent",
            name="is_family_event",
            field=models.BooleanField(default=False),
        ),
        migrations.RunPython(migrate_legacy_member_assignments, migrations.RunPython.noop),
    ]
