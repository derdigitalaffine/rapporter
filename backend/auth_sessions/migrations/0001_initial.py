# Generated manually for the isolated auth session app.

import uuid

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True

    dependencies = [migrations.swappable_dependency(settings.AUTH_USER_MODEL)]

    operations = [
        migrations.CreateModel(
            name="AuthSession",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("auth_method", models.CharField(choices=[("password", "Password"), ("passkey", "Passkey"), ("recovery", "Recovery")], default="password", max_length=24)),
                ("client_label", models.CharField(blank=True, max_length=120)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("last_seen_at", models.DateTimeField()),
                ("last_reauthenticated_at", models.DateTimeField()),
                ("absolute_expires_at", models.DateTimeField(db_index=True)),
                ("refresh_expires_at", models.DateTimeField()),
                ("current_refresh_jti", models.CharField(blank=True, max_length=64)),
                ("previous_refresh_jti", models.CharField(blank=True, max_length=64)),
                ("previous_refresh_valid_until", models.DateTimeField(blank=True, null=True)),
                ("last_rotated_at", models.DateTimeField(blank=True, null=True)),
                ("revoked_at", models.DateTimeField(blank=True, db_index=True, null=True)),
                ("revoked_reason", models.CharField(blank=True, max_length=64)),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="auth_sessions", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "ordering": ["-last_seen_at", "-created_at"],
                "indexes": [models.Index(fields=["user", "revoked_at", "absolute_expires_at"], name="auth_session_user_active")],
            },
        ),
    ]
