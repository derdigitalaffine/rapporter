import uuid

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="WebAuthnChallenge",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("ceremony", models.CharField(choices=[("register", "Register"), ("authenticate", "Authenticate"), ("reauthenticate", "Reauthenticate")], max_length=24)),
                ("challenge", models.BinaryField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("expires_at", models.DateTimeField(db_index=True)),
                ("consumed_at", models.DateTimeField(blank=True, null=True)),
                ("user", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="webauthn_challenges", to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name="WebAuthnCredential",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("credential_id", models.BinaryField(unique=True)),
                ("public_key", models.BinaryField()),
                ("sign_count", models.PositiveBigIntegerField(default=0)),
                ("name", models.CharField(max_length=120)),
                ("transports", models.JSONField(blank=True, default=list)),
                ("device_type", models.CharField(blank=True, max_length=32)),
                ("backed_up", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("last_used_at", models.DateTimeField(blank=True, null=True)),
                ("revoked_at", models.DateTimeField(blank=True, db_index=True, null=True)),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="webauthn_credentials", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-last_used_at", "-created_at"]},
        ),
        migrations.AddIndex(
            model_name="webauthnchallenge",
            index=models.Index(fields=["ceremony", "expires_at"], name="passkey_chal_exp_idx"),
        ),
        migrations.AddIndex(
            model_name="webauthncredential",
            index=models.Index(fields=["user", "revoked_at"], name="passkey_user_active_idx"),
        ),
    ]
