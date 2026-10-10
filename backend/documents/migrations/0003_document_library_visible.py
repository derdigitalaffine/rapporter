from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("documents", "0002_document_processing"),
    ]

    operations = [
        migrations.AddField(
            model_name="document",
            name="library_visible",
            field=models.BooleanField(db_index=True, default=True),
        ),
    ]
