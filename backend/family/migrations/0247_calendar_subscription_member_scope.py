from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('family', '0246_shopping_reference_dataset')]

    operations = [
        migrations.AddField(
            model_name='calendarsubscription',
            name='included_member_ids',
            field=models.JSONField(blank=True, default=list),
        ),
    ]
