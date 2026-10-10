import uuid

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("family", "0210_context_links"),
    ]

    operations = [
        migrations.CreateModel(
            name="AuditEvent",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("occurred_at", models.DateTimeField(db_index=True, default=django.utils.timezone.now)),
                ("event_key", models.CharField(db_index=True, max_length=96)),
                ("schema_version", models.PositiveSmallIntegerField(default=1)),
                ("actor_class", models.CharField(choices=[("user", "User"), ("superadmin", "Superadmin"), ("system", "System")], max_length=16)),
                ("target_type", models.CharField(blank=True, max_length=32)),
                ("target_id", models.CharField(blank=True, max_length=128)),
                ("outcome", models.CharField(choices=[("success", "Success"), ("denied", "Denied"), ("failed", "Failed")], max_length=16)),
                ("reason", models.CharField(blank=True, max_length=64)),
                ("request_id", models.CharField(blank=True, max_length=64)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("actor", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="audit_events", to=settings.AUTH_USER_MODEL)),
                ("family", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="audit_events", to="family.family")),
            ],
            options={"ordering": ["-occurred_at", "id"]},
        ),
        migrations.CreateModel(
            name="UsageEvent",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("occurred_at", models.DateTimeField(db_index=True, default=django.utils.timezone.now)),
                ("bucket_start", models.DateTimeField(db_index=True)),
                ("event_key", models.CharField(db_index=True, max_length=64)),
                ("dimension_key", models.CharField(blank=True, max_length=64)),
                ("family", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="usage_events", to="family.family")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="usage_events", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-bucket_start", "id"]},
        ),
        migrations.CreateModel(
            name="DailyRollup",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("day", models.DateField(db_index=True)),
                ("metric_key", models.CharField(max_length=96)),
                ("dimension_key", models.CharField(blank=True, max_length=160)),
                ("value", models.BigIntegerField(default=0)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("family", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="telemetry_rollups", to="family.family")),
            ],
            options={"ordering": ["-day", "metric_key", "dimension_key", "id"]},
        ),
        migrations.AddIndex(
            model_name="auditevent",
            index=models.Index(fields=["event_key", "occurred_at"], name="audit_event_key_time"),
        ),
        migrations.AddIndex(
            model_name="auditevent",
            index=models.Index(fields=["family", "occurred_at"], name="audit_family_time"),
        ),
        migrations.AddIndex(
            model_name="auditevent",
            index=models.Index(fields=["actor", "occurred_at"], name="audit_actor_time"),
        ),
        migrations.AddIndex(
            model_name="auditevent",
            index=models.Index(fields=["outcome", "occurred_at"], name="audit_outcome_time"),
        ),
        migrations.AddIndex(
            model_name="usageevent",
            index=models.Index(fields=["event_key", "bucket_start"], name="usage_event_key_bucket"),
        ),
        migrations.AddIndex(
            model_name="usageevent",
            index=models.Index(fields=["family", "bucket_start"], name="usage_family_bucket"),
        ),
        migrations.AddIndex(
            model_name="usageevent",
            index=models.Index(fields=["user", "bucket_start"], name="usage_user_bucket"),
        ),
        migrations.AddIndex(
            model_name="dailyrollup",
            index=models.Index(fields=["day", "metric_key"], name="rollup_day_metric"),
        ),
        migrations.AddIndex(
            model_name="dailyrollup",
            index=models.Index(fields=["family", "day"], name="rollup_family_day"),
        ),
        migrations.AddConstraint(
            model_name="usageevent",
            constraint=models.UniqueConstraint(fields=("user", "family", "event_key", "bucket_start", "dimension_key"), name="usage_event_bucket_unique"),
        ),
        migrations.AddConstraint(
            model_name="dailyrollup",
            constraint=models.UniqueConstraint(fields=("day", "metric_key", "family", "dimension_key"), name="daily_rollup_unique", nulls_distinct=False),
        ),
    ]
