# Generated manually to keep the scheduling slice reviewable.
import uuid

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("family", "0231_family_relationships"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="SchedulingSeries",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("target_type", models.CharField(choices=[("calendar.event", "Calendar event"), ("action", "Action")], max_length=32)),
                ("target_id", models.UUIDField()),
                ("status", models.CharField(choices=[("active", "Active"), ("paused", "Paused"), ("ended", "Ended")], db_index=True, default="active", max_length=16)),
                ("current_version", models.PositiveIntegerField(default=1)),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="created_scheduling_series", to=settings.AUTH_USER_MODEL)),
                ("family", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="scheduling_series", to="family.family")),
            ],
        ),
        migrations.CreateModel(
            name="SchedulingRuleVersion",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("version", models.PositiveIntegerField()),
                ("rule", models.JSONField()),
                ("change_scope", models.CharField(choices=[("initial", "Initial"), ("whole", "Whole series"), ("future", "This and future")], default="initial", max_length=16)),
                ("effective_from", models.DateField(blank=True, null=True)),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="created_scheduling_rule_versions", to=settings.AUTH_USER_MODEL)),
                ("series", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="rule_versions", to="family.schedulingseries")),
            ],
            options={"ordering": ["version"]},
        ),
        migrations.CreateModel(
            name="SchedulingOccurrenceOverride",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("occurrence_key", models.CharField(max_length=96)),
                ("kind", models.CharField(choices=[("skip", "Skip"), ("override", "Override"), ("detach", "Detach")], max_length=16)),
                ("payload", models.JSONField(blank=True, default=dict)),
                ("detached_fields", models.JSONField(blank=True, default=list)),
                ("rule_version", models.PositiveIntegerField(blank=True, null=True)),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="created_scheduling_occurrence_overrides", to=settings.AUTH_USER_MODEL)),
                ("series", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="occurrence_overrides", to="family.schedulingseries")),
            ],
        ),
        migrations.CreateModel(
            name="SchedulingDependency",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("anchor_type", models.CharField(max_length=32)),
                ("anchor_id", models.UUIDField()),
                ("anchor_scope", models.CharField(choices=[("series", "Series"), ("occurrence", "Occurrence")], default="series", max_length=16)),
                ("anchor_occurrence_key", models.CharField(blank=True, max_length=96)),
                ("output_type", models.CharField(choices=[("calendar.event", "Calendar event"), ("action", "Action"), ("notification", "Notification")], max_length=32)),
                ("output_blueprint", models.JSONField(blank=True, default=dict)),
                ("relative_rule", models.JSONField()),
                ("inheritance", models.JSONField(blank=True, default=dict)),
                ("conflict_policy", models.JSONField(blank=True, default=dict)),
                ("enabled", models.BooleanField(db_index=True, default=True)),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="created_scheduling_dependencies", to=settings.AUTH_USER_MODEL)),
                ("family", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="scheduling_dependencies", to="family.family")),
            ],
        ),
        migrations.CreateModel(
            name="SchedulingTemplate",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("scope", models.CharField(choices=[("personal", "Personal"), ("family", "Family"), ("admin", "Admin managed")], default="personal", max_length=16)),
                ("name", models.CharField(max_length=120)),
                ("rule", models.JSONField()),
                ("dependency_blueprint", models.JSONField(blank=True, default=dict)),
                ("locked", models.BooleanField(default=False)),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="created_scheduling_templates", to=settings.AUTH_USER_MODEL)),
                ("family", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="scheduling_templates", to="family.family")),
                ("owner", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="scheduling_templates", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["name", "created_at"]},
        ),
        migrations.AddConstraint(
            model_name="schedulingseries",
            constraint=models.UniqueConstraint(fields=("family", "target_type", "target_id"), name="schedule_series_target_unique"),
        ),
        migrations.AddIndex(
            model_name="schedulingseries",
            index=models.Index(fields=["family", "target_type", "target_id"], name="schedule_series_target_idx"),
        ),
        migrations.AddIndex(
            model_name="schedulingseries",
            index=models.Index(fields=["family", "status"], name="schedule_series_status_idx"),
        ),
        migrations.AddConstraint(
            model_name="schedulingruleversion",
            constraint=models.UniqueConstraint(fields=("series", "version"), name="schedule_rule_version_unique"),
        ),
        migrations.AddConstraint(
            model_name="schedulingruleversion",
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(change_scope="future", effective_from__isnull=False)
                    | models.Q(change_scope__in=["initial", "whole"], effective_from__isnull=True)
                ),
                name="schedule_rule_scope_effective_valid",
            ),
        ),
        migrations.AddIndex(
            model_name="schedulingruleversion",
            index=models.Index(fields=["series", "effective_from", "version"], name="schedule_rule_effective_idx"),
        ),
        migrations.AddConstraint(
            model_name="schedulingoccurrenceoverride",
            constraint=models.UniqueConstraint(fields=("series", "occurrence_key"), name="schedule_occurrence_unique"),
        ),
        migrations.AddIndex(
            model_name="schedulingoccurrenceoverride",
            index=models.Index(fields=["series", "occurrence_key"], name="schedule_occurrence_idx"),
        ),
        migrations.AddConstraint(
            model_name="schedulingdependency",
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(anchor_scope="series", anchor_occurrence_key="")
                    | (models.Q(anchor_scope="occurrence") & ~models.Q(anchor_occurrence_key=""))
                ),
                name="schedule_dependency_scope_key_valid",
            ),
        ),
        migrations.AddIndex(
            model_name="schedulingdependency",
            index=models.Index(fields=["family", "anchor_type", "anchor_id"], name="schedule_dependency_anchor_idx"),
        ),
        migrations.AddIndex(
            model_name="schedulingdependency",
            index=models.Index(fields=["family", "enabled"], name="schedule_dep_enabled_idx"),
        ),
        migrations.AddConstraint(
            model_name="schedulingtemplate",
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(scope="personal", owner__isnull=False)
                    | models.Q(scope__in=["family", "admin"], owner__isnull=True)
                ),
                name="schedule_template_scope_owner_valid",
            ),
        ),
        migrations.AddConstraint(
            model_name="schedulingtemplate",
            constraint=models.UniqueConstraint(
                condition=models.Q(scope="personal"),
                fields=("family", "owner", "name"),
                name="schedule_template_personal_name_unique",
            ),
        ),
        migrations.AddConstraint(
            model_name="schedulingtemplate",
            constraint=models.UniqueConstraint(
                condition=models.Q(scope__in=["family", "admin"]),
                fields=("family", "scope", "name"),
                name="schedule_template_shared_name_unique",
            ),
        ),
        migrations.AddIndex(
            model_name="schedulingtemplate",
            index=models.Index(fields=["family", "scope", "name"], name="schedule_template_scope_idx"),
        ),
    ]
