import uuid

from django.conf import settings
from django.db import models


class WebAuthnCredential(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="webauthn_credentials",
    )
    credential_id = models.BinaryField(unique=True)
    public_key = models.BinaryField()
    sign_count = models.PositiveBigIntegerField(default=0)
    name = models.CharField(max_length=120)
    transports = models.JSONField(default=list, blank=True)
    device_type = models.CharField(max_length=32, blank=True)
    backed_up = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    last_used_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True, db_index=True)

    class Meta:
        ordering = ["-last_used_at", "-created_at"]
        indexes = [
            models.Index(fields=["user", "revoked_at"], name="passkey_user_active_idx"),
        ]


class WebAuthnChallenge(models.Model):
    class Ceremony(models.TextChoices):
        REGISTER = "register", "Register"
        AUTHENTICATE = "authenticate", "Authenticate"
        REAUTHENTICATE = "reauthenticate", "Reauthenticate"

    class Context(models.TextChoices):
        APP = "app", "App"
        SUPERADMIN = "superadmin", "Superadmin"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="webauthn_challenges",
    )
    ceremony = models.CharField(max_length=24, choices=Ceremony.choices)
    context = models.CharField(max_length=24, choices=Context.choices, default=Context.APP)
    challenge = models.BinaryField()
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(db_index=True)
    consumed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["ceremony", "context", "expires_at"], name="passkey_chal_ctx_exp_idx"),
        ]
