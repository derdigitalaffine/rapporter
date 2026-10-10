from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("family", "0211_boardpost_routine_shopping_list_kinds")]

    operations = [
        migrations.AlterField(
            model_name="boardpost",
            name="kind",
            field=models.CharField(
                choices=[
                    ("note", "Note"),
                    ("photo", "Photo"),
                    ("event", "Calendar event"),
                    ("task", "Task"),
                    ("routine", "Routine"),
                    ("note_ref", "Note reference"),
                    ("shopping", "Shopping item"),
                    ("shopping_list", "Shopping list"),
                    ("trip", "Trip"),
                ],
                default="note",
                max_length=16,
            ),
        ),
    ]
