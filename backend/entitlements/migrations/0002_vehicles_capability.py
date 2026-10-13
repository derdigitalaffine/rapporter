from django.db import migrations


def seed(apps, schema_editor):
    apps.get_model("entitlements", "CapabilityDefinition").objects.update_or_create(
        key="vehicles", defaults={"domain": "vehicles", "description": "Fahrzeuge und privates GPS-Fahrtenbuch", "premium": True, "default_light": False, "deprecated": False},
    )


class Migration(migrations.Migration):
    dependencies = [("entitlements", "0001_initial")]
    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
