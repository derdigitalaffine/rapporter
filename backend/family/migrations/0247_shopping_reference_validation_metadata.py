from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("family", "0246_shopping_reference_dataset"),
    ]

    operations = [
        migrations.AddField(
            model_name="referencedataset",
            name="source_adapter",
            field=models.CharField(blank=True, default="", max_length=64),
        ),
        migrations.AddField(
            model_name="referencedataset",
            name="package_size_bytes",
            field=models.PositiveBigIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="referencedataset",
            name="record_count",
            field=models.PositiveBigIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="referencedataset",
            name="validation_summary",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name="referencedataset",
            name="validation_error",
            field=models.TextField(blank=True),
        ),
    ]
