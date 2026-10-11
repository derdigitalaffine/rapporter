from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("auth_identity", "0002_backfill_unique_user_emails"),
    ]

    operations = [
        migrations.AddField(
            model_name="emailidentity",
            name="password_reset_requested_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="emailidentity",
            name="password_reset_version",
            field=models.PositiveIntegerField(default=0),
        ),
    ]
