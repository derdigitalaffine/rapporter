from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('family', '0245_shopping_item_create_receipt')]

    operations = [
        migrations.AddField(
            model_name='calendarsubscription',
            name='included_member_ids',
            field=models.JSONField(blank=True, default=list),
        ),
    ]
