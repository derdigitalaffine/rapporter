import uuid

from django.conf import settings
from django.db import models


class AuthSession(models.Model):
    class AuthMethod(models.TextChoices):
        PASSWORD = "password", "Password"
        PASSKEY = "passkey", "Passkey"
        RECOVERY = "recovery", "Recovery"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="auth_sessions")
    auth_method = models.CharField(max_length=24, choices=AuthMethod.choices, default=AuthMethod.PASSWORD)
    client_label = models.CharField(max_length=120, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_seen_at = models.DateTimeField()
    last_reauthenticated_at = models.DateTimeField()
    absolute_expires_at = models.DateTimeField(db_index=True)
    refresh_expires_at = models.DateTimeField()
    current_refresh_jti = models.CharField(max_length=64, blank=True)
    previous_refresh_jti = models.CharField(max_length=64, blank=True)
    previous_refresh_valid_until = models.DateTimeField(null=True, blank=True)
    last_rotated_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True, db_index=True)
    revoked_reason = models.CharField(max_length=64, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["user", "revoked_at", "absolute_expires_at"], name="auth_session_user_active"),
        ]
        ordering = ["-last_seen_at", "-created_at"]

    @property
    def is_revoked(self):
        return self.revoked_at is not None
