import uuid

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("family", "0247_shopping_reference_validation_metadata"),
    ]

    operations = [
        migrations.AddField(
            model_name="referencedataset",
            name="state_revision",
            field=models.PositiveBigIntegerField(default=0),
        ),
        migrations.AddConstraint(
            model_name="referencedataset",
            constraint=models.UniqueConstraint(
                condition=models.Q(state="active"),
                fields=("dataset_id",),
                name="refds_one_active_uniq",
            ),
        ),
        migrations.CreateModel(
            name="ReferenceDatasetLease",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("dataset_id", models.CharField(max_length=180, unique=True)),
                ("owner", models.CharField(max_length=128)),
                ("token", models.UUIDField(default=uuid.uuid4, editable=False)),
                ("expires_at", models.DateTimeField()),
            ],
            options={
                "ordering": ["dataset_id"],
            },
        ),
        migrations.CreateModel(
            name="ReferenceDatasetActivationEvent",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("dataset_id", models.CharField(db_index=True, max_length=180)),
                (
                    "action",
                    models.CharField(
                        choices=[
                            ("activate", "Activate"),
                            ("disable", "Disable"),
                            ("rollback", "Rollback"),
                        ],
                        max_length=16,
                    ),
                ),
                ("from_version", models.CharField(blank=True, max_length=80)),
                ("to_version", models.CharField(blank=True, max_length=80)),
                ("state_revision", models.PositiveBigIntegerField(default=0)),
                ("reason_code", models.CharField(blank=True, max_length=80)),
            ],
            options={
                "ordering": ["-created_at", "-id"],
                "indexes": [
                    models.Index(fields=["dataset_id", "-created_at"], name="refds_event_time_idx"),
                ],
            },
        ),
    ]
