from django.core.exceptions import ValidationError
from django.db import models

from .models import Family, Membership, TimestampedModel


class FamilyRelationship(TimestampedModel):
    """Descriptive relationship between one child and one family member.

    Relationship facts deliberately carry no authorization semantics. Family
    role, account guardianship and Pregnancy/Baby Care Circle permissions are
    separate contracts.
    """

    class Kind(models.TextChoices):
        PARENT = "parent", "Elternteil"
        MOTHER = "mother", "Mutter"
        FATHER = "father", "Vater"
        BONUS_PARENT = "bonus_parent", "Bonus-Elternteil"
        BONUS_MOTHER = "bonus_mother", "Bonusmutter"
        BONUS_FATHER = "bonus_father", "Bonusvater"
        ADOPTIVE_PARENT = "adoptive_parent", "Adoptiv-Elternteil"
        ADOPTIVE_MOTHER = "adoptive_mother", "Adoptivmutter"
        ADOPTIVE_FATHER = "adoptive_father", "Adoptivvater"
        FOSTER_PARENT = "foster_parent", "Pflege-Elternteil"
        FOSTER_MOTHER = "foster_mother", "Pflegemutter"
        FOSTER_FATHER = "foster_father", "Pflegevater"
        GRANDPARENT = "grandparent", "Großelternteil"
        SIBLING = "sibling", "Geschwister"
        OTHER = "other", "Andere Beziehung"
        NONE = "none", "Keine Bezeichnung"

    class Status(models.TextChoices):
        ACTIVE = "active", "Aktiv"
        INACTIVE = "inactive", "Inaktiv"

    class ChildVisibility(models.TextChoices):
        FULL = "full", "Vollständig"
        RELATIONSHIP_ONLY = "relationship_only", "Nur Beziehung"
        HIDDEN = "hidden", "Für das Kind verborgen"

    family = models.ForeignKey(Family, on_delete=models.CASCADE, related_name="family_relationships")
    child_membership = models.ForeignKey(
        Membership,
        on_delete=models.CASCADE,
        related_name="family_relationships_as_child",
    )
    related_membership = models.ForeignKey(
        Membership,
        on_delete=models.CASCADE,
        related_name="family_relationships_to_children",
    )
    kind = models.CharField(max_length=32, choices=Kind.choices, default=Kind.PARENT)
    custom_label = models.CharField(max_length=80, blank=True)
    is_biological_parent = models.BooleanField(default=False)
    is_legal_parent = models.BooleanField(default=False)
    has_custody = models.BooleanField(null=True, blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.ACTIVE)
    child_visibility = models.CharField(
        max_length=24,
        choices=ChildVisibility.choices,
        default=ChildVisibility.RELATIONSHIP_ONLY,
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["family", "child_membership", "related_membership"],
                name="family_unique_child_relation_member",
            )
        ]
        indexes = [
            models.Index(
                fields=["child_membership", "status"],
                name="family_rel_child_status_idx",
            )
        ]

    def clean(self):
        errors = {}
        if self.child_membership_id and self.related_membership_id and self.child_membership_id == self.related_membership_id:
            errors["related_membership"] = "Eine Person kann nicht ihre eigene Familienbeziehung sein."
        if self.family_id and self.child_membership_id and self.child_membership.family_id != self.family_id:
            errors["child_membership"] = "Das Kind muss zur selben Familie gehören."
        if self.family_id and self.related_membership_id and self.related_membership.family_id != self.family_id:
            errors["related_membership"] = "Die Bezugsperson muss zur selben Familie gehören."
        if self.child_membership_id and self.child_membership.role != Membership.Role.CHILD:
            errors["child_membership"] = "Familienbeziehungen können nur einem Kind zugeordnet werden."
        if errors:
            raise ValidationError(errors)

    @property
    def display_label(self):
        custom = self.custom_label.strip()
        if custom:
            return custom
        if self.kind == self.Kind.NONE:
            return ""
        return self.get_kind_display()
