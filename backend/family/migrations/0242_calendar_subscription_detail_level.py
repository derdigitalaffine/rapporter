from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('family', '0241_calendar_subscription')]

    operations = [
        migrations.AddField(
            model_name='calendarsubscription',
            name='detail_level',
            field=models.CharField(
                choices=[
                    ('busy', 'Availability only'),
                    ('basic', 'Title and time'),
                    ('full', 'Full event details'),
                ],
                default='basic',
                max_length=16,
            ),
        ),
    ]
