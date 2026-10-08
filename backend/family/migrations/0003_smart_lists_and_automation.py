from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import uuid


def create_defaults(apps, schema_editor):
    Family = apps.get_model("family", "Family")
    TaskList = apps.get_model("family", "TaskList")
    Task = apps.get_model("family", "Task")
    AutomationRule = apps.get_model("family", "AutomationRule")
    for family in Family.objects.all():
        task_list, _ = TaskList.objects.get_or_create(family=family, name="Allgemein", defaults={"icon": "list-check"})
        Task.objects.filter(family=family, task_list__isnull=True).update(task_list=task_list)
        AutomationRule.objects.get_or_create(
            family=family,
            name="Müll rausstellen",
            defaults={
                "icon": "trash-can",
                "enabled": True,
                "trigger_type": "waste_tomorrow",
                "trigger_config": {},
                "action_type": "task_create",
                "action_config": {"title": "{event_title} rausstellen", "priority": "normal"},
            },
        )


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("family", "0002_familyinvitation"),
    ]

    operations = [
        migrations.CreateModel(
            name="TaskList",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("name", models.CharField(max_length=120)),
                ("icon", models.CharField(default="list-check", max_length=48)),
                ("archived", models.BooleanField(default=False)),
                ("sort_order", models.PositiveIntegerField(default=0)),
                ("family", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="task_lists", to="family.family")),
            ],
            options={"ordering": ["sort_order", "created_at"], "unique_together": {("family", "name")}},
        ),
        migrations.AddField(model_name="task", name="estimate_minutes", field=models.PositiveIntegerField(blank=True, null=True)),
        migrations.AddField(model_name="task", name="tags", field=models.JSONField(blank=True, default=list)),
        migrations.AddField(model_name="task", name="task_list", field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="tasks", to="family.tasklist")),
        migrations.AddField(model_name="shoppinglist", name="icon", field=models.CharField(default="cart-shopping", max_length=48)),
        migrations.AddField(model_name="shoppinglist", name="sort_order", field=models.PositiveIntegerField(default=0)),
        migrations.AddField(model_name="shoppingitem", name="aisle", field=models.CharField(blank=True, max_length=80)),
        migrations.AddField(model_name="shoppingitem", name="checked_at", field=models.DateTimeField(blank=True, null=True)),
        migrations.AddField(model_name="shoppingitem", name="favorite", field=models.BooleanField(default=False)),
        migrations.AddField(model_name="shoppingitem", name="note", field=models.CharField(blank=True, max_length=240)),
        migrations.CreateModel(
            name="AutomationRule",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("name", models.CharField(max_length=160)),
                ("icon", models.CharField(default="wand-magic-sparkles", max_length=48)),
                ("enabled", models.BooleanField(default=True)),
                ("trigger_type", models.CharField(choices=[("waste_tomorrow", "Waste collection tomorrow"), ("weather_frost", "Frost forecast"), ("weather_rain", "Rain forecast"), ("warning_active", "Official warning active"), ("event_upcoming", "Upcoming event"), ("daily", "Daily at time")], max_length=40)),
                ("trigger_config", models.JSONField(blank=True, default=dict)),
                ("action_type", models.CharField(choices=[("task_create", "Create task"), ("shopping_add", "Add shopping item"), ("inbox_create", "Create inbox message")], max_length=40)),
                ("action_config", models.JSONField(blank=True, default=dict)),
                ("last_run_at", models.DateTimeField(blank=True, null=True)),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="automation_rules_created", to=settings.AUTH_USER_MODEL)),
                ("family", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="automation_rules", to="family.family")),
            ],
        ),
        migrations.CreateModel(
            name="AutomationExecution",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("fingerprint", models.CharField(max_length=220)),
                ("status", models.CharField(default="success", max_length=20)),
                ("message", models.CharField(blank=True, max_length=500)),
                ("rule", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="executions", to="family.automationrule")),
            ],
            options={"ordering": ["-created_at"], "unique_together": {("rule", "fingerprint")}},
        ),
        migrations.RunPython(create_defaults, migrations.RunPython.noop),
    ]
