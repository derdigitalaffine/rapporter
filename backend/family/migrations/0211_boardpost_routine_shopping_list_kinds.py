from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('family', '0210_context_links')]

    operations = [
        migrations.AlterField(
            model_name='boardpost',
            name='kind',
            field=models.CharField(
                choices=[
                    ('note', 'Note'),
                    ('photo', 'Photo'),
                    ('event', 'Calendar event'),
                    ('task', 'Task'),
                    ('routine', 'Routine'),
                    ('note_ref', 'Note reference'),
                    ('shopping', 'Shopping item'),
                    ('shopping_list', 'Shopping list'),
                ],
                default='note',
                max_length=16,
            ),
        ),
    ]
