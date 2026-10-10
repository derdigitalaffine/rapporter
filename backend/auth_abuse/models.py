from django.db import models


class AuthAbuseBucket(models.Model):
    scope = models.CharField(max_length=64)
    key_hash = models.CharField(max_length=64)
    key_kind = models.CharField(max_length=32)
    window_kind = models.CharField(max_length=16)
    window_seconds = models.PositiveIntegerField()
    window_started_at = models.DateTimeField()
    count = models.PositiveIntegerField(default=0)
    penalty_level = models.PositiveSmallIntegerField(default=0)
    blocked_until = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["scope", "key_hash", "window_kind"],
                name="auth_abuse_bucket_unique",
            )
        ]
        indexes = [
            models.Index(fields=["scope", "key_hash"], name="auth_abuse_scope_key"),
        ]
