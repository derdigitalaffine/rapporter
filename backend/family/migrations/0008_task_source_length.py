from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("family", "0007_entry_memory")]

    operations = [
        migrations.AlterField(
            model_name="task",
            name="source",
            field=models.CharField(default="manual", max_length=96),
        ),
    ]
