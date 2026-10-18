from family.family_relationship_models import FamilyRelationship
from family.models import Membership


def grant_test_custody(user, baby):
    """Explicit fixture authority; never infer it from child creation or Owner."""
    membership = Membership.objects.get(user=user, family=baby.family)
    row, _ = FamilyRelationship.objects.get_or_create(
        family=baby.family, child_membership=baby.membership, related_membership=membership, kind="parent",
        defaults={"has_custody": True, "status": "active"},
    )
    return row
