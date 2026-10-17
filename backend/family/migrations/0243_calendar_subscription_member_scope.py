from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('family', '0242_caldav_access_mode_member')]

    operations = [
        migrations.AddField(
            model_name='calendarsubscription',
            name='included_member_ids',
            field=models.JSONField(blank=True, default=list),
        ),
    ]
