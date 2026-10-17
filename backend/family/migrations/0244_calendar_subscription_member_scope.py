from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('family', '0243_shopping_store_location_reference')]

    operations = [
        migrations.AddField(
            model_name='calendarsubscription',
            name='included_member_ids',
            field=models.JSONField(blank=True, default=list),
        ),
    ]
