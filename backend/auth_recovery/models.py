from django.conf import settings
from django.db import models


class PasswordResetState(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="password_reset_state",
    )
    identity = models.ForeignKey(
        "auth_identity.EmailIdentity",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    version = models.PositiveBigIntegerField(default=0)
    requested_at = models.DateTimeField(null=True, blank=True)
    consumed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["requested_at"], name="auth_recovery_requested"),
        ]
