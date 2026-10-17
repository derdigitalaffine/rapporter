from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("messenger", "0005_migrate_family_inbox_to_chat")]
    operations = [migrations.AddField(model_name="chatmessage", name="location", field=models.JSONField(blank=True, null=True))]
