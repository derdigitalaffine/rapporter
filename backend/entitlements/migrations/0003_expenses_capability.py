from django.db import migrations


def seed(apps, schema_editor):
    apps.get_model("entitlements", "CapabilityDefinition").objects.update_or_create(
        key="expenses", defaults={"domain": "expenses", "description": "Geld & Finanzen", "premium": True, "default_light": False, "deprecated": False},
    )


class Migration(migrations.Migration):
    dependencies = [("entitlements", "0002_vehicles_capability")]
    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
