from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("family", "0237_shopping_session_live_sync"),
    ]

    operations = [
        migrations.AddField(
            model_name="shoppingsession",
            name="snapshot",
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
