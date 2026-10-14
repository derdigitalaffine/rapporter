from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("auth_sessions", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="authsession",
            name="surface",
            field=models.CharField(
                choices=[("app", "App"), ("superadmin", "Superadmin")],
                db_index=True,
                default="app",
                max_length=24,
            ),
        ),
    ]
