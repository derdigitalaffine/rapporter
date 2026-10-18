from django.db import migrations, models
import django.db.models.deletion


def guard_reverse(apps, schema_editor):
    records = apps.get_model("baby", "ChildHealthRecord")
    if records.objects.using(schema_editor.connection.alias).filter(reminder_task__isnull=False).exists():
        raise RuntimeError("Keep the reminder schema during a UI rollback. Explicitly reconcile private task associations before reversing this migration.")


class Migration(migrations.Migration):
    dependencies = [
        ("baby", "0006_alter_pediatricpreventiveeventreference_rule_key"),
    ]
    operations = [
        migrations.AddField(
            model_name="childhealthrecord",
            name="reminder_task",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                                    related_name="child_health_records", to="family.task"),
        ),
        migrations.RunPython(migrations.RunPython.noop, guard_reverse),
    ]
