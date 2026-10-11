from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("family", "0215_birthday_occasion_context"),
    ]

    operations = [
        migrations.AddField(
            model_name="trip",
            name="participants",
            field=models.ManyToManyField(blank=True, related_name="travel_trips", to="family.membership"),
        ),
    ]
