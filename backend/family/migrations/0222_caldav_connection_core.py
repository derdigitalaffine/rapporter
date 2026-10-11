import django.db.models.deletion
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("family", "0221_pass_core"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="CalDavConnection",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("scope", models.CharField(choices=[("personal", "Personal"), ("family", "Family")], max_length=16)),
                ("name", models.CharField(max_length=120)),
                ("credentials_encrypted", models.TextField(blank=True, editable=False)),
                ("enabled", models.BooleanField(default=True)),
                ("last_discovered_at", models.DateTimeField(blank=True, null=True)),
                ("last_error_code", models.CharField(blank=True, max_length=64)),
                ("created_by", models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="created_caldav_connections", to=settings.AUTH_USER_MODEL)),
                ("family", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="caldav_connections", to="family.family")),
                ("owner", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="personal_caldav_connections", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["name", "created_at"]},
        ),
        migrations.AddConstraint(
            model_name="caldavconnection",
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(("family__isnull", True), ("owner__isnull", False), ("scope", "personal"))
                    | models.Q(("family__isnull", False), ("owner__isnull", True), ("scope", "family"))
                ),
                name="caldav_scope_owner_exactly_one",
            ),
        ),
        migrations.AddIndex(
            model_name="caldavconnection",
            index=models.Index(fields=["owner", "enabled"], name="caldav_owner_enabled_idx"),
        ),
        migrations.AddIndex(
            model_name="caldavconnection",
            index=models.Index(fields=["family", "enabled"], name="caldav_family_enabled_idx"),
        ),
    ]
