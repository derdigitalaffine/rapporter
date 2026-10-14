# Generated manually to keep the scheduling runtime slice reviewable.
import uuid

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("family", "0232_scheduling_series_metadata"),
    ]

    operations = [
        migrations.CreateModel(
            name="SchedulingMaterialization",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("anchor_occurrence_key", models.CharField(max_length=96)),
                ("output_type", models.CharField(max_length=32)),
                ("output_id", models.UUIDField(blank=True, null=True)),
                ("scheduled_for", models.DateTimeField()),
                ("dedupe_key", models.CharField(max_length=64)),
                ("status", models.CharField(choices=[("projected", "Projected"), ("materialized", "Materialized"), ("skipped", "Skipped"), ("detached", "Detached")], default="projected", max_length=16)),
                ("projected_payload", models.JSONField(blank=True, default=dict)),
                ("provenance", models.JSONField(blank=True, default=dict)),
                ("dependency", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="materializations", to="family.schedulingdependency")),
                ("family", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="scheduling_materializations", to="family.family")),
            ],
        ),
        migrations.AddConstraint(
            model_name="schedulingmaterialization",
            constraint=models.UniqueConstraint(fields=("family", "dedupe_key"), name="schedule_mat_dedupe_unique"),
        ),
        migrations.AddIndex(
            model_name="schedulingmaterialization",
            index=models.Index(fields=["dependency", "scheduled_for"], name="schedule_mat_dep_time_idx"),
        ),
        migrations.AddIndex(
            model_name="schedulingmaterialization",
            index=models.Index(fields=["family", "output_type", "output_id"], name="schedule_mat_output_idx"),
        ),
    ]
