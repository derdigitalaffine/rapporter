import uuid

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("family", "0249_merge_calendar_subscription_and_shopping_reference"),
    ]

    operations = [
        migrations.CreateModel(
            name="ReferenceDatasetRecord",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("record_key", models.CharField(max_length=256)),
                ("source_path", models.CharField(max_length=500)),
                ("ordinal", models.PositiveBigIntegerField()),
                ("payload", models.JSONField(default=dict)),
                ("lookup_key", models.CharField(blank=True, max_length=255)),
                ("tombstone", models.BooleanField(default=False)),
                (
                    "dataset",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="records",
                        to="family.referencedataset",
                    ),
                ),
            ],
            options={
                "ordering": ["ordinal", "id"],
                "indexes": [
                    models.Index(fields=["dataset", "tombstone"], name="refrec_dataset_live_idx"),
                    models.Index(fields=["dataset", "lookup_key"], name="refrec_lookup_idx"),
                ],
                "constraints": [
                    models.UniqueConstraint(fields=("dataset", "record_key"), name="refrec_dataset_key_uniq"),
                ],
            },
        ),
        migrations.CreateModel(
            name="ReferenceDatasetSearchTerm",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("term", models.CharField(max_length=200)),
                (
                    "kind",
                    models.CharField(
                        choices=[
                            ("primary", "Primary"),
                            ("alias", "Alias"),
                            ("code", "Code"),
                            ("id", "ID"),
                        ],
                        default="primary",
                        max_length=16,
                    ),
                ),
                (
                    "dataset",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="search_terms",
                        to="family.referencedataset",
                    ),
                ),
                (
                    "record",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="search_terms",
                        to="family.referencedatasetrecord",
                    ),
                ),
            ],
            options={
                "ordering": ["term", "id"],
                "indexes": [
                    models.Index(fields=["dataset", "term"], name="refterm_dataset_term_idx"),
                ],
                "constraints": [
                    models.UniqueConstraint(fields=("record", "term"), name="refterm_record_term_uniq"),
                ],
            },
        ),
    ]
