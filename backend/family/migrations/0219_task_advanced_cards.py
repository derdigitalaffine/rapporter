import django.db.models.deletion
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("family", "0218_note_extended_mode_blocks"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="TaskChecklistItem",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("title", models.CharField(max_length=180)),
                ("position", models.PositiveIntegerField(default=0)),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
                ("extracted_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="created_task_checklist_items", to=settings.AUTH_USER_MODEL)),
                ("extracted_task", models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="source_checklist_item", to="family.task")),
                ("task", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="checklist_items", to="family.task")),
            ],
            options={"ordering": ["position", "created_at", "id"], "indexes": [models.Index(fields=["task", "position"], name="task_checklist_order_idx")]},
        ),
        migrations.CreateModel(
            name="TaskExternalLink",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("url", models.URLField(max_length=2048)),
                ("label", models.CharField(blank=True, max_length=120)),
                ("position", models.PositiveIntegerField(default=0)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="created_task_external_links", to=settings.AUTH_USER_MODEL)),
                ("task", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="external_links", to="family.task")),
            ],
            options={
                "ordering": ["position", "created_at", "id"],
                "indexes": [models.Index(fields=["task", "position"], name="task_external_order_idx")],
                "constraints": [models.UniqueConstraint(fields=("task", "url"), name="task_external_link_url_uniq")],
            },
        ),
    ]
