from django.core.exceptions import ValidationError
from django.db import models

from .models import Family, Membership, TimestampedModel


class FamilyRelationship(TimestampedModel):
    """A descriptive relationship between one child and one family member.

    This model deliberately carries no authorization semantics. Family role,
    account guardianship and Pregnancy/Baby Care Circle permissions remain
    separate contracts