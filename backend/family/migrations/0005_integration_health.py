from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("family", "0004_extended_integrations_and_rules")]

    operations = [
        migrations.AddField(model_name="integrationsource", name="last_attempt_at", field=models.DateTimeField(blank=True, null=True)),
        migrations.AddField(model_name="integrationsource", name="last_success_at", field=models.DateTimeField(blank=True, null=True)),
        migrations.AddField(model_name="integrationsource", name="last_sync_status", field=models.CharField(default="never", max_length=16)),
        migrations.AddField(model_name="integrationsource", name="last_sync_error", field=models.TextField(blank=True)),
        migrations.AddField(model_name="integrationsource", name="consecutive_failures", field=models.PositiveIntegerField(default=0)),
        migrations.AddField(model_name="integrationsource", name="next_sync_at", field=models.DateTimeField(blank=True, null=True)),
    ]
