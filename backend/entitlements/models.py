import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q


class CapabilityDefinition(models.Model):
    key = models.SlugField(max_length=96, primary_key=True)
    domain = models.SlugField(max_length=64)
    description = models.CharField(max_length=240)
    default_light = models.BooleanField(default=False)
    premium = models.BooleanField(default=False)
    deprecated = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["key"]


class EntitlementGrant(models.Model):
    class Origin(models.TextChoices):
        PURCHASED_LIFETIME = "purchased_lifetime", "Purchased lifetime"
        ADMIN_GRANT = "admin_grant", "Admin grant"
        LEGACY_GRANDFATHERED = "legacy_grandfathered", "Legacy grandfathered"
        SUBSCRIPTION = "subscription", "Subscription"
        PROMOTION = "promotion", "Promotion"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    family = models.ForeignKey("family.Family", on_delete=models.CASCADE, related_name="entitlement_grants")
    origin = models.CharField(max_length=32, choices=Origin.choices)
    plan_key = models.SlugField(max_length=64, blank=True)
    capability_set = models.JSONField(default=list, blank=True)
    starts_at = models.DateTimeField(null=True, blank=True)
    ends_at = models.DateTimeField(null=True, blank=True)
    active = models.BooleanField(default=True)
    source_ref = models.CharField(max_length=160, null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="entitlement_grants_created",
    )
    reason = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at", "id"]
        constraints = [
            models.CheckConstraint(
                condition=Q(revoked_at__isnull=True) | Q(active=False),
                name="ent_grant_revoked_inactive",
            ),
            models.UniqueConstraint(
                fields=["family", "origin", "source_ref"],
                condition=Q(source_ref__isnull=False),
                name="ent_grant_source_unique",
            ),
        ]
        indexes = [
            models.Index(fields=["family", "active"], name="ent_grant_family_active"),
            models.Index(fields=["family", "ends_at"], name="ent_grant_family_ends"),
        ]


class EntitlementGrantAudit(models.Model):
    class Action(models.TextChoices):
        GRANTED = "granted", "Granted"
        REVOKED = "revoked", "Revoked"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    grant = models.ForeignKey(EntitlementGrant, on_delete=models.CASCADE, related_name="audit_events")
    family = models.ForeignKey("family.Family", on_delete=models.CASCADE, related_name="entitlement_audit_events")
    action = models.CharField(max_length=16, choices=Action.choices)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="entitlement_audit_events",
    )
    reason = models.CharField(max_length=500, blank=True)
    snapshot = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "id"]
        indexes = [models.Index(fields=["family", "-created_at"], name="ent_audit_family_created")]
