from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from .models import BirthdayPerson, Family, Membership, TimestampedModel


class BirthdayOccasion(TimestampedModel):
    """Stable yearly planning anchor without duplicating canonical birthday dates."""

    family = models.ForeignKey(Family, on_delete=models.CASCADE, related_name="birthday_occasions")
    membership = models.ForeignKey(
        Membership,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="birthday_occasions",
    )
    person = models.ForeignKey(
        BirthdayPerson,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="occasions",
    )
    occurrence_year = models.PositiveSmallIntegerField()
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_birthday_occasions",
    )
    planning_started_at = models.DateTimeField(null=True, blank=True)
    reminder_settings = models.JSONField(null=True, blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(membership__isnull=False, person__isnull=True)
                    | models.Q(membership__isnull=True, person__isnull=False)
                ),
                name="birthday_occasion_one_target",
            ),
            models.UniqueConstraint(
                fields=["membership", "occurrence_year"],
                name="birthday_occasion_member_year_unique",
            ),
            models.UniqueConstraint(
                fields=["person", "occurrence_year"],
                name="birthday_occasion_person_year_unique",
            ),
        ]

    def clean(self):
        super().clean()
        if bool(self.membership_id) == bool(self.person_id):
            raise ValidationError("Birthday occasion needs exactly one target person.")
        if self.family_id and self.membership_id and self.membership.family_id != self.family_id:
            raise ValidationError({"membership": "Membership belongs to another family."})
        if self.family_id and self.person_id and self.person.family_id != self.family_id:
            raise ValidationError({"person": "Birthday person belongs to another family."})

    def save(self, *args, **kwargs):
        # Related-family equality cannot be expressed as a portable SQL CHECK.
        # Enforce it on every normal ORM write in addition to the DB target/unique constraints.
        self.full_clean()
        return super().save(*args, **kwargs)
