from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('family', '0242_caldav_access_mode_member')]

    operations = [
        migrations.AddField(
            model_name='shoppingstore',
            name='location_provider',
            field=models.CharField(blank=True, max_length=32),
        ),
        migrations.AddField(
            model_name='shoppingstore',
            name='location_ref',
            field=models.CharField(blank=True, max_length=160),
        ),
        migrations.AddField(
            model_name='shoppingstore',
            name='latitude',
            field=models.DecimalField(blank=True, decimal_places=6, max_digits=9, null=True),
        ),
        migrations.AddField(
            model_name='shoppingstore',
            name='longitude',
            field=models.DecimalField(blank=True, decimal_places=6, max_digits=9, null=True),
        ),
        migrations.AddConstraint(
            model_name='shoppingstore',
            constraint=models.UniqueConstraint(
                condition=models.Q(location_provider__gt='', location_ref__gt=''),
                fields=('family', 'location_provider', 'location_ref'),
                name='shop_store_location_ref_uniq',
            ),
        ),
    ]
