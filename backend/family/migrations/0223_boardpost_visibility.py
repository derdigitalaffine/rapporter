from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('family', '0222_caldav_connection_core'),
    ]

    operations = [
        migrations.AddField(
            model_name='boardpost',
            name='visibility',
            field=models.CharField(
                choices=[
                    ('private', 'Private'),
                    ('selected', 'Selected members'),
                    ('family', 'Whole family'),
                ],
                db_index=True,
                default='family',
                max_length=16,
            ),
        ),
        migrations.AddField(
            model_name='boardpost',
            name='visible_to_memberships',
            field=models.ManyToManyField(
                blank=True,
                related_name='visible_board_posts',
                to='family.membership',
            ),
        ),
    ]
