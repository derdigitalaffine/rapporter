from datetime import date

from django.db import migrations, models


CUTOVER_DATE = date(2026, 10, 10)


def backfill_trip_lifecycle(apps, schema_editor):
    Trip = apps.get_model("family", "Trip")
    concrete = Trip.objects.filter(
        starts_on__isnull=False,
        ends_on__isnull=False,
        date_precision="exact",
    )
    concrete.filter(archived=True).update(stage="archived")
    concrete.filter(archived=False, ends_on__lt=CUTOVER_DATE).update(stage="completed")
    concrete.filter(
        archived=False,
        starts_on__lte=CUTOVER_DATE,
        ends_on__gte=CUTOVER_DATE,
    ).update(stage="active")
    concrete.filter(archived=False, starts_on__gt=CUTOVER_DATE).update(stage="scheduled")


class Migration(migrations.Migration):
    dependencies = [("family", "0212_boardpost_trip_kind")]

    operations = [
        migrations.AddField(
            model_name="trip",
            name="stage",
            field=models.CharField(
                choices=[
                    ("idea", "Idea"),
                    ("planning", "Planning"),
                    ("scheduled", "Scheduled"),
                    ("active", "Active"),
                    ("completed", "Completed"),
                    ("archived", "Archived"),
                ],
                default="planning",
                max_length=16,
            ),
        ),
        migrations.AddField(
            model_name="trip",
            name="date_precision",
            field=models.CharField(
                choices=[
                    ("unknown", "Unknown"),
                    ("year", "Year"),
                    ("season", "Season"),
                    ("month", "Month"),
                    ("range", "Range"),
                    ("exact", "Exact"),
                ],
                default="exact",
                max_length=16,
            ),
        ),
        migrations.AddField(
            model_name="trip",
            name="date_year",
            field=models.PositiveSmallIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="trip",
            name="date_month",
            field=models.PositiveSmallIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="trip",
            name="date_season",
            field=models.CharField(
                blank=True,
                choices=[
                    ("spring", "Spring"),
                    ("summer", "Summer"),
                    ("autumn", "Autumn"),
                    ("winter", "Winter"),
                ],
                max_length=8,
            ),
        ),
        migrations.AlterField(
            model_name="trip",
            name="starts_on",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name="trip",
            name="ends_on",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.RunPython(backfill_trip_lifecycle, migrations.RunPython.noop),
    ]
