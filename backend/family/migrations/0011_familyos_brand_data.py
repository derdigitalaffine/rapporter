from django.db import migrations


def forwards(apps, schema_editor):
    FamilyEvent = apps.get_model("family", "FamilyEvent")
    for event in FamilyEvent.objects.filter(type="calendar.event").iterator():
        payload = dict(event.payload or {})
        if payload.get("provider") in {"fam-uh-le", "fam-uh-le"} or not payload.get("provider"):
            payload["provider"] = "FamilyOS"
            event.payload = payload
            event.save(update_fields=["payload"])

    AutomationRule = apps.get_model("family", "AutomationRule")
    for rule in AutomationRule.objects.all().iterator():
        config = dict(rule.action_config or {})
        changed = False
        for key in ("title", "body"):
            value = config.get(key)
            if isinstance(value, str) and "fam-uh-le" in value:
                config[key] = value.replace("fam-uh-le", "FamilyOS")
                changed = True
        if changed:
            rule.action_config = config
            rule.save(update_fields=["action_config"])


def backwards(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [("family", "0010_family_status")]
    operations = [migrations.RunPython(forwards, backwards)]
