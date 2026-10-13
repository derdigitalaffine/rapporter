from django.db.models.signals import post_save
from django.dispatch import receiver

from .family_relationship_models import FamilyRelationship
from .models import Membership


@receiver(post_save, sender="baby.BabyProfile")
def create_default_creator_relationship(sender, instance, created, **kwargs):
    """Seed the explicit default selected by the managed-child creation flow.

    The creator is described as biological + legal parent by default. This
    creates relationship facts only; account/care permissions remain untouched.
    """
    if not created or not instance.created_by_id or not instance.membership_id:
        return
    creator_membership = Membership.objects.filter(
        family_id=instance.family_id,
        user_id=instance.created_by_id,
    ).first()
    if not creator_membership:
        return
    FamilyRelationship.objects.get_or_create(
        family_id=instance.family_id,
        child_membership_id=instance.membership_id,
        related_membership=creator_membership,
        defaults={
            "kind": FamilyRelationship.Kind.PARENT,
            "is_biological_parent": True,
            "is_legal_parent": True,
            "has_custody": None,
            "status": FamilyRelationship.Status.ACTIVE,
            "child_visibility": FamilyRelationship.ChildVisibility.RELATIONSHIP_ONLY,
        },
    )
