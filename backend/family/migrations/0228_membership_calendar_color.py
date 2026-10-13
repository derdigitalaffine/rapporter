from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("family", "0227_birthday_age_preferences")]

    operations = [
        migrations.AddField(
            model_name="membership",
            name="calendar_color",
            field=models.CharField(blank=True, default="", max_length=7),
        ),
    ]
