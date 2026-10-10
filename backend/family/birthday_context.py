from django.core.exceptions import ValidationError

from .birthday_context_models import BirthdayOccasion
from .context_links import create_context_link


def get_or_create_birthday_occasion(
    *,
    family,
    occurrence_year,
    membership=None,
    person=None,
    created_by=None,
):
    """Return the single stable planning anchor for one birthday target/year."""
    if bool(membership) == bool(person):
        raise ValidationError("Birthday occasion needs exactly one target person.")
    target = membership or person
    if target.family_id != family.id:
        raise ValidationError("Birthday target belongs to another family.")
    lookup = {"membership": membership} if membership else {"person": person}
    return BirthdayOccasion.objects.get_or_create(
        family=family,
        occurrence_year=occurrence_year,
        **lookup,
        defaults={"created_by": created_by},
    )


def sync_birthday_gift_plan_context(plan, *, user=None):
    """Keep legacy BirthdayGiftPlan links and the canonical ContextLink graph in sync.

    Existing `birthday_context` UUID fields keep their legacy GiftPlan id. The
    BirthdayOccasion is additive and becomes the stable source for new generic
    links. During data migration `user` is unknown, so only the occasion is
    created here; the migration backfills historical links directly.
    """
    occasion, _ = get_or_create_birthday_occasion(
        family=plan.family,
        occurrence_year=plan.occurrence_year,
        membership=plan.membership,
        person=plan.person,
        created_by=user,
    )
    if user and plan.linked_task_id:
        create_context_link(
            user=user,
            family=plan.family,
            source_type="birthday_occasion",
            source_id=occasion.id,
            context_type="task",
            context_id=plan.linked_task_id,
            relation_key="birthday.gift_task",
        )
    if user and plan.linked_shopping_item_id:
        create_context_link(
            user=user,
            family=plan.family,
            source_type="birthday_occasion",
            source_id=occasion.id,
            context_type="shopping_item",
            context_id=plan.linked_shopping_item_id,
            relation_key="birthday.shopping_item",
        )
    return occasion
