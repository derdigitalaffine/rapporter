import uuid

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def backfill_birthday_occasions(apps, schema_editor):
    BirthdayGiftPlan = apps.get_model("family", "BirthdayGiftPlan")
    BirthdayOccasion = apps.get_model("family", "BirthdayOccasion")
    Membership = apps.get_model("family", "Membership")
    BirthdayPerson = apps.get_model("family", "BirthdayPerson")
    Task = apps.get_model("family", "Task")
    ShoppingItem = apps.get_model("family", "ShoppingItem")
    ContextLink = apps.get_model("family", "ContextLink")

    for plan in BirthdayGiftPlan.objects.all().iterator():
        lookup = None
        if plan.membership_id:
            same_family = Membership.objects.filter(pk=plan.membership_id, family_id=plan.family_id).exists()
            if same_family:
                lookup = {"membership_id": plan.membership_id, "person_id": None}
        elif plan.person_id:
            same_family = BirthdayPerson.objects.filter(pk=plan.person_id, family_id=plan.family_id).exists()
            if same_family:
                lookup = {"membership_id": None, "person_id": plan.person_id}
        if lookup is None:
            # Preserve dirty legacy rows rather than inventing a cross-family anchor.
            continue

        occasion, _ = BirthdayOccasion.objects.get_or_create(
            family_id=plan.family_id,
            occurrence_year=plan.occurrence_year,
            **lookup,
        )

        if plan.linked_task_id and Task.objects.filter(pk=plan.linked_task_id, family_id=plan.family_id).exists():
            ContextLink.objects.get_or_create(
                family_id=plan.family_id,
                source_type="birthday_occasion",
                source_id=occasion.id,
                context_type="task",
                context_id=plan.linked_task_id,
                relation_key="birthday.gift_task",
            )

        if plan.linked_shopping_item_id and ShoppingItem.objects.filter(
            pk=plan.linked_shopping_item_id,
            shopping_list__family_id=plan.family_id,
        ).exists():
            ContextLink.objects.get_or_create(
                family_id=plan.family_id,
                source_type="birthday_occasion",
                source_id=occasion.id,
                context_type="shopping_item",
                context_id=plan.linked_shopping_item_id,
                relation_key="birthday.shopping_item",
            )


def reverse_birthday_occasions(apps, schema_editor):
    ContextLink = apps.get_model("family", "ContextLink")
    ContextLink.objects.filter(source_type="birthday_occasion").delete()
    ContextLink.objects.filter(context_type="birthday_occasion").delete()


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("family", "0214_boardpost_document_kind"),
    ]

    operations = [
        migrations.CreateModel(
            name="BirthdayOccasion",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("occurrence_year", models.PositiveSmallIntegerField()),
                ("planning_started_at", models.DateTimeField(blank=True, null=True)),
                ("reminder_settings", models.JSONField(blank=True, null=True)),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="created_birthday_occasions",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "family",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="birthday_occasions",
                        to="family.family",
                    ),
                ),
                (
                    "membership",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="birthday_occasions",
                        to="family.membership",
                    ),
                ),
                (
                    "person",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="occasions",
                        to="family.birthdayperson",
                    ),
                ),
            ],
            options={
                "constraints": [
                    models.CheckConstraint(
                        condition=(
                            models.Q(membership__isnull=False, person__isnull=True)
                            | models.Q(membership__isnull=True, person__isnull=False)
                        ),
                        name="birthday_occasion_one_target",
                    ),
                    models.UniqueConstraint(
                        fields=("membership", "occurrence_year"),
                        name="birthday_occasion_member_year_unique",
                    ),
                    models.UniqueConstraint(
                        fields=("person", "occurrence_year"),
                        name="birthday_occasion_person_year_unique",
                    ),
                ]
            },
        ),
        migrations.RunPython(backfill_birthday_occasions, reverse_birthday_occasions),
    ]
