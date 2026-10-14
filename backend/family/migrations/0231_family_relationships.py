import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("family", "0230_familyevent_participants_family_marker"),
    ]

    operations = [
        migrations.CreateModel(
            name="FamilyRelationship",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "kind",
                    models.CharField(
                        choices=[
                            ("parent", "Elternteil"),
                            ("mother", "Mutter"),
                            ("father", "Vater"),
                            ("bonus_parent", "Bonus-Elternteil"),
                            ("bonus_mother", "Bonusmutter"),
                            ("bonus_father", "Bonusvater"),
                            ("adoptive_parent", "Adoptiv-Elternteil"),
                            ("adoptive_mother", "Adoptivmutter"),
                            ("adoptive_father", "Adoptivvater"),
                            ("foster_parent", "Pflege-Elternteil"),
                            ("foster_mother", "Pflegemutter"),
                            ("foster_father", "Pflegevater"),
                            ("grandparent", "Großelternteil"),
                            ("sibling", "Geschwister"),
                            ("other", "Andere Beziehung"),
                            ("none", "Keine Bezeichnung"),
                        ],
                        default="parent",
                        max_length=32,
                    ),
                ),
                ("custom_label", models.CharField(blank=True, max_length=80)),
                ("is_biological_parent", models.BooleanField(default=False)),
                ("is_legal_parent", models.BooleanField(default=False)),
                ("has_custody", models.BooleanField(blank=True, null=True)),
                (
                    "status",
                    models.CharField(
                        choices=[("active", "Aktiv"), ("inactive", "Inaktiv")],
                        default="active",
                        max_length=16,
                    ),
                ),
                (
                    "child_visibility",
                    models.CharField(
                        choices=[
                            ("full", "Vollständig"),
                            ("relationship_only", "Nur Beziehung"),
                            ("hidden", "Für das Kind verborgen"),
                        ],
                        default="relationship_only",
                        max_length=24,
                    ),
                ),
                (
                    "child_membership",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="family_relationships_as_child",
                        to="family.membership",
                    ),
                ),
                (
                    "family",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="family_relationships",
                        to="family.family",
                    ),
                ),
                (
                    "related_membership",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="family_relationships_to_children",
                        to="family.membership",
                    ),
                ),
            ],
        ),
        migrations.AddConstraint(
            model_name="familyrelationship",
            constraint=models.UniqueConstraint(
                fields=("family", "child_membership", "related_membership"),
                name="family_unique_child_relation_member",
            ),
        ),
        migrations.AddIndex(
            model_name="familyrelationship",
            index=models.Index(
                fields=["child_membership", "status"],
                name="family_rel_child_status_idx",
            ),
        ),
    ]
