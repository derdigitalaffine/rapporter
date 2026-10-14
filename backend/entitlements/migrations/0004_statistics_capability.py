from django.db import migrations


def seed(apps, schema_editor):
    apps.get_model("entitlements", "CapabilityDefinition").objects.update_or_create(
        key="statistics", defaults={"domain": "statistics", "description": "Statistik / Family Insights", "premium": True, "default_light": False, "deprecated": False})


class Migration(migrations.Migration):
    dependencies = [("entitlements", "0003_expenses_capability")]
    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
