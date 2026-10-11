from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('family', '0217_merge_trip_invitation'),
    ]

    operations = [
        migrations.AddField(
            model_name='note',
            name='extended_mode',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='note',
            name='blocks',
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name='noterevision',
            name='extended_mode',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='noterevision',
            name='blocks',
            field=models.JSONField(blank=True, default=list),
        ),
    ]
