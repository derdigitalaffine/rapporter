import uuid

from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):
    dependencies = [
        ("documents", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="DocumentProcessingRun",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("status", models.CharField(choices=[("queued", "Queued"), ("processing", "Processing"), ("retry", "Retry"), ("review", "Review"), ("ready", "Ready"), ("failed", "Failed")], db_index=True, default="queued", max_length=16)),
                ("pipeline_version", models.CharField(default="1", max_length=32)),
                ("extractor", models.CharField(blank=True, max_length=64)),
                ("language", models.CharField(blank=True, max_length=24)),
                ("normalized_text", models.TextField(blank=True)),
                ("quality_data", models.JSONField(blank=True, default=dict)),
                ("attempts", models.PositiveIntegerField(default=0)),
                ("claim_token", models.UUIDField(blank=True, editable=False, null=True)),
                ("queued_at", models.DateTimeField(db_index=True, default=django.utils.timezone.now)),
                ("started_at", models.DateTimeField(blank=True, null=True)),
                ("processing_started_at", models.DateTimeField(blank=True, null=True)),
                ("lease_expires_at", models.DateTimeField(blank=True, db_index=True, null=True)),
                ("next_retry_at", models.DateTimeField(blank=True, db_index=True, null=True)),
                ("processed_at", models.DateTimeField(blank=True, null=True)),
                ("error_code", models.CharField(blank=True, max_length=64)),
                ("safe_error", models.CharField(blank=True, max_length=240)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("document", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="processing_runs", to="documents.document")),
            ],
            options={
                "ordering": ["queued_at", "created_at"],
            },
        ),
        migrations.CreateModel(
            name="ExtractedField",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("key", models.CharField(max_length=96)),
                ("value_json", models.JSONField()),
                ("confidence", models.DecimalField(decimal_places=4, default=0, max_digits=5)),
                ("page", models.PositiveIntegerField(blank=True, null=True)),
                ("bbox", models.JSONField(blank=True, null=True)),
                ("evidence_text", models.TextField(blank=True)),
                ("source_type", models.CharField(choices=[("explicit", "Explicit"), ("derived", "Derived")], default="explicit", max_length=16)),
                ("extractor_version", models.CharField(default="1", max_length=64)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("processing_run", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="extracted_fields", to="documents.documentprocessingrun")),
            ],
            options={
                "ordering": ["key", "page", "created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="documentprocessingrun",
            index=models.Index(fields=["status", "next_retry_at", "queued_at"], name="docproc_status_retry_idx"),
        ),
        migrations.AddIndex(
            model_name="documentprocessingrun",
            index=models.Index(fields=["status", "lease_expires_at"], name="docproc_lease_idx"),
        ),
        migrations.AddIndex(
            model_name="extractedfield",
            index=models.Index(fields=["processing_run", "key"], name="docfield_run_key_idx"),
        ),
        migrations.AddConstraint(
            model_name="extractedfield",
            constraint=models.CheckConstraint(condition=models.Q(("confidence__gte", 0), ("confidence__lte", 1)), name="docfield_confidence_0_1"),
        ),
    ]
