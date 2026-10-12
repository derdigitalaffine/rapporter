import uuid

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("family", "0222_caldav_connection_core"),
    ]

    operations = [
        migrations.CreateModel(
            name="CreateActionPreference",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("smart_ranking_enabled", models.BooleanField(default=True)),
                ("context_ranking_enabled", models.BooleanField(default=True)),
                ("time_patterns_enabled", models.BooleanField(default=False)),
                ("direct_mode", models.BooleanField(default=False)),
                ("direct_action_id", models.CharField(blank=True, max_length=48)),
                ("max_quick_actions", models.PositiveSmallIntegerField(default=4)),
                ("pinned_action_ids", models.JSONField(blank=True, default=list)),
                ("hidden_action_ids", models.JSONField(blank=True, default=list)),
                ("manual_order", models.JSONField(blank=True, default=list)),
                ("learning_scope", models.CharField(choices=[("family", "Family"), ("global", "Global")], default="family", max_length=16)),
                ("membership", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="create_action_preference", to="family.membership")),
            ],
        ),
        migrations.CreateModel(
            name="CreateActionStat",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("action_id", models.CharField(max_length=48)),
                ("use_count", models.PositiveIntegerField(default=0)),
                ("last_used_at", models.DateTimeField(blank=True, null=True)),
                ("context_stats", models.JSONField(blank=True, default=dict)),
                ("time_bucket_stats", models.JSONField(blank=True, default=dict)),
                ("membership", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="create_action_stats", to="family.membership")),
            ],
            options={
                "indexes": [models.Index(fields=["membership", "last_used_at"], name="create_stat_member_used_idx")],
                "constraints": [models.UniqueConstraint(fields=("membership", "action_id"), name="create_action_stat_member_id_uniq")],
            },
        ),
        migrations.CreateModel(
            name="CreateActionUsageReceipt",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("event_id", models.UUIDField(unique=True)),
                ("action_id", models.CharField(max_length=48)),
                ("origin_page", models.CharField(blank=True, max_length=32)),
                ("context_bucket", models.CharField(blank=True, max_length=32)),
                ("membership", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="create_action_usage_receipts", to="family.membership")),
            ],
            options={
                "indexes": [models.Index(fields=["membership", "created_at"], name="create_receipt_member_at_idx")],
            },
        ),
    ]
