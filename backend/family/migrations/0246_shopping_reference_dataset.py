import uuid

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("family", "0245_shopping_item_create_receipt"),
    ]

    operations = [
        migrations.CreateModel(
            name="ReferenceDataset",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("dataset_id", models.CharField(max_length=180)),
                (
                    "dataset_type",
                    models.CharField(
                        choices=[
                            ("store_reference", "Store reference"),
                            ("lexicon", "Lexicon"),
                            ("gtin_product", "GTIN product"),
                            ("store_layout_evidence", "Store layout evidence"),
                        ],
                        max_length=40,
                    ),
                ),
                ("schema_version", models.PositiveIntegerField()),
                ("version", models.CharField(max_length=80)),
                ("source_url", models.URLField(blank=True, max_length=1000)),
                ("source_revision", models.CharField(blank=True, max_length=200)),
                ("locale", models.CharField(blank=True, max_length=32)),
                ("country", models.CharField(blank=True, max_length=2)),
                ("region", models.CharField(blank=True, max_length=120)),
                ("licence", models.CharField(max_length=120)),
                ("attribution", models.TextField(blank=True)),
                (
                    "redistribution",
                    models.CharField(
                        choices=[
                            ("adopt", "Adopt"),
                            ("adapt", "Adapt"),
                            ("defer", "Defer"),
                            ("deny", "Deny"),
                        ],
                        max_length=16,
                    ),
                ),
                ("checksum", models.CharField(max_length=128)),
                ("coverage", models.JSONField(blank=True, default=dict)),
                ("quality", models.JSONField(blank=True, default=dict)),
                ("dependencies", models.JSONField(blank=True, default=list)),
                ("manifest", models.JSONField(blank=True, default=dict)),
                (
                    "state",
                    models.CharField(
                        choices=[
                            ("staged", "Staged"),
                            ("validating", "Validating"),
                            ("preview", "Preview"),
                            ("activating", "Activating"),
                            ("active", "Active"),
                            ("failed", "Failed"),
                            ("stale", "Stale / update available"),
                            ("disabled", "Disabled"),
                            ("rollback", "Rollback"),
                        ],
                        db_index=True,
                        default="staged",
                        max_length=24,
                    ),
                ),
                ("fetched_at", models.DateTimeField(blank=True, null=True)),
                ("verified_at", models.DateTimeField(blank=True, null=True)),
                ("installed_at", models.DateTimeField(blank=True, null=True)),
                ("validated_at", models.DateTimeField(blank=True, null=True)),
                ("activated_at", models.DateTimeField(blank=True, null=True)),
            ],
            options={
                "ordering": ["dataset_id", "-created_at"],
                "indexes": [
                    models.Index(fields=["dataset_type", "state"], name="refds_type_state_idx"),
                    models.Index(fields=["dataset_id", "state"], name="refds_id_state_idx"),
                ],
                "constraints": [
                    models.UniqueConstraint(fields=("dataset_id", "version"), name="refds_id_version_uniq"),
                ],
            },
        ),
    ]
