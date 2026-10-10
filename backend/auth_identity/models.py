from django.conf import settings
from django.db import models


class EmailIdentity(models.Model):
    class Kind(models.TextChoices):
        PRIMARY = "primary", "Primary"
        PENDING = "pending", "Pending"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="email_identities",
    )
    kind = models.CharField(max_length=16, choices=Kind.choices, default=Kind.PRIMARY)
    email = models.EmailField(max_length=254)
    email_normalized = models.CharField(max_length=254, unique=True)
    verified_at = models.DateTimeField(null=True, blank=True)
    verification_sent_at = models.DateTimeField(null=True, blank=True)
    verification_version = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "kind"],
                name="auth_identity_user_kind_unique",
            )
        ]
        indexes = [
            models.Index(fields=["user", "kind"], name="auth_identity_user_kind"),
        ]

    @property
    def is_verified(self):
        return self.verified_at is not None
