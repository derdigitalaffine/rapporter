from django.db import migrations, models
import django.db.models.deletion


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
    ]
