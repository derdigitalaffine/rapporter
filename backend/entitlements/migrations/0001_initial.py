import uuid

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
from django.db.models import Q


CAPABILITIES = (
    ("family_management", "family", "Familien- und Mitgliederverwaltung", True, False),
    ("calendar", "calendar", "Gemeinsamer Familienkalender", True, False),
    ("todo", "todo", "Basis-Aufgaben und Routinen", True, False),
    ("shopping", "shopping", "Gemeinsame Einkaufslisten", True, False),
    ("pinboard", "pinboard", "Universelle Familien-Pinnwand", True, False),
    ("notes", "notes", "Einfache Familiennotizen", True, False),
    ("travel", "travel", "Reiseplanung und Travel Hub", False, True),
    ("documents", "documents", "Document Core und Dokument-Workflows", False, True),
    ("school", "school", "Schule und Lernintegrationen", False, True),
    ("children", "children", "Kinder- und Vorsorge-Power-Features", False, True),
    ("pregnancy_baby", "baby", "Schwangerschaft und Baby-Power-Features", False, True),
    ("pets", "pets", "Haustier-Power-Features", False, True),
    ("advanced_integrations", "integrations", "Erweiterte Integrationen", False, True),
    ("advanced_tasks", "todo", "Erweiterte Task-/Workflow-Funktionen", False, True),
)


def seed_capabilities(apps, schema_editor):
    CapabilityDefinition = apps.get_model("entitlements", "CapabilityDefinition")
    for key, domain, description, default_light, premium in CAPABILITIES:
        CapabilityDefinition.objects.update_or_create(
            key=key,
            defaults={
                "domain": domain,
                "description": description,
                "default_light": default_light,
                "premium": premium,
                "deprecated": False,
            },
        )


class Migration(migrations.Migration):
    initial = True
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("family", "0209_pinboard"),
    ]

    operations = [
        migrations.CreateModel(
            name="CapabilityDefinition",
            fields=[
                ("key", models.SlugField(max_length=96, primary_key=True, serialize=False)),
                ("domain", models.SlugField(max_length=64)),
                ("description", models.CharField(max_length=240)),
                ("default_light", models.BooleanField(default=False)),
                ("premium", models.BooleanField(default=False)),
                ("deprecated", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"ordering": ["key"]},
        ),
        migrations.CreateModel(
            name="EntitlementCutover",
            fields=[
                ("key", models.SlugField(max_length=64, primary_key=True, serialize=False)),
                ("cutover_at", models.DateTimeField()),
                ("applied_at", models.DateTimeField()),
                ("eligible_family_count", models.PositiveIntegerField(default=0)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
        ),
        migrations.CreateModel(
            name="EntitlementGrant",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("origin", models.CharField(choices=[("purchased_lifetime", "Purchased lifetime"), ("admin_grant", "Admin grant"), ("legacy_grandfathered", "Legacy grandfathered"), ("subscription", "Subscription"), ("promotion", "Promotion")], max_length=32)),
                ("plan_key", models.SlugField(blank=True, max_length=64)),
                ("capability_set", models.JSONField(blank=True, default=list)),
                ("starts_at", models.DateTimeField(blank=True, null=True)),
                ("ends_at", models.DateTimeField(blank=True, null=True)),
                ("active", models.BooleanField(default=True)),
                ("source_ref", models.CharField(blank=True, max_length=160, null=True)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("reason", models.CharField(blank=True, max_length=500)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("revoked_at", models.DateTimeField(blank=True, null=True)),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="entitlement_grants_created", to=settings.AUTH_USER_MODEL)),
                ("family", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="entitlement_grants", to="family.family")),
            ],
            options={
                "ordering": ["-created_at", "id"],
                "indexes": [models.Index(fields=["family", "active"], name="ent_grant_family_active"), models.Index(fields=["family", "ends_at"], name="ent_grant_family_ends")],
                "constraints": [
                    models.CheckConstraint(condition=Q(("revoked_at__isnull", True), ("active", False), _connector="OR"), name="ent_grant_revoked_inactive"),
                    models.UniqueConstraint(condition=Q(("source_ref__isnull", False)), fields=("family", "origin", "source_ref"), name="ent_grant_source_unique"),
                ],
            },
        ),
        migrations.CreateModel(
            name="EntitlementGrantAudit",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("action", models.CharField(choices=[("granted", "Granted"), ("revoked", "Revoked")], max_length=16)),
                ("reason", models.CharField(blank=True, max_length=500)),
                ("snapshot", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("actor", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="entitlement_audit_events", to=settings.AUTH_USER_MODEL)),
                ("family", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="entitlement_audit_events", to="family.family")),
                ("grant", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="audit_events", to="entitlements.entitlementgrant")),
            ],
            options={
                "ordering": ["-created_at", "id"],
                "indexes": [models.Index(fields=["family", "-created_at"], name="ent_audit_family_created")],
            },
        ),
        migrations.RunPython(seed_capabilities, migrations.RunPython.noop),
    ]
