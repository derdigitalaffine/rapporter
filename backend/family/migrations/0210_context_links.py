import uuid

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("family", "0209_pinboard"),
    ]

    operations = [
        migrations.CreateModel(
            name="ContextLink",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("source_type", models.CharField(max_length=64)),
                ("source_id", models.UUIDField()),
                ("context_type", models.CharField(max_length=64)),
                ("context_id", models.UUIDField()),
                ("relation_key", models.SlugField(max_length=64)),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="created_context_links",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "family",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="context_links",
                        to="family.family",
                    ),
                ),
            ],
            options={
                "ordering": ["created_at", "id"],
                "indexes": [
                    models.Index(fields=["family", "source_type", "source_id"], name="ctx_link_source_idx"),
                    models.Index(fields=["family", "context_type", "context_id"], name="ctx_link_context_idx"),
                ],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("family", "source_type", "source_id", "context_type", "context_id", "relation_key"),
                        name="context_link_unique",
                    ),
                ],
            },
        ),
    ]
