from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('family', '0244_shopping_activity_client_order')]

    operations = [
        migrations.AddField(
            model_name='calendarsubscription',
            name='included_member_ids',
            field=models.JSONField(blank=True, default=list),
        ),
    ]
