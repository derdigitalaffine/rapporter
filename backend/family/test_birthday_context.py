import importlib

from django.apps import apps as django_apps
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from rest_framework.test import APIClient

from .birthday_context import get_or_create_birthday_occasion
from .birthday_context_models import BirthdayOccasion
from .context_links import ContextObjectUnavailable, create_context_link, list_context_links
from .context_models import ContextLink
from .models import (
    BirthdayGiftPlan,
    BirthdayPerson,
    Family,
    FamilyEvent,
    Membership,
    ShoppingItem,
    ShoppingList,
    Task,
    UserProfile,
)


class BirthdayOccasionContextTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user(username="occasion-owner")
        self.target = User.objects.create_user(username="occasion-target")
        self.viewer = User.objects.create_user(username="occasion-viewer")
        self.other_user = User.objects.create_user(username="occasion-other")
        self.family = Family.objects.create(name="Occasion", slug="occasion")
        self.other_family = Family.objects.create(name="Other", slug="occasion-other")
        Membership.objects.create(family=self.family, user=self.owner, role=Membership.Role.OWNER)
        self.target_member = Membership.objects.create(
            family=self.family,
            user=self.target,
            role=Membership.Role.ADULT,
            display_name="Mia",
            birthday_visibility=Membership.BirthdayVisibility.DAY_MONTH,
        )
        Membership.objects.create(family=self.family, user=self.viewer, role=Membership.Role.TEEN)
        self.other_member = Membership.objects.create(
            family=self.other_family,
            user=self.other_user,
            role=Membership.Role.OWNER,
        )
        UserProfile.objects.create(user=self.target, birth_month=12, birth_day=1, birth_year=2016)
        self.client = APIClient()
        self.client.force_authenticate(self.owner)

    def test_single_anchor_per_target_year_without_second_birthday_date(self):
        member_occasion, created = get_or_create_birthday_occasion(
            family=self.family,
            membership=self.target_member,
            occurrence_year=2027,
            created_by=self.owner,
        )
        same, created_again = get_or_create_birthday_occasion(
            family=self.family,
            membership=self.target_member,
            occurrence_year=2027,
            created_by=self.viewer,
        )
        self.assertTrue(created)
        self.assertFalse(created_again)
        self.assertEqual(member_occasion.id, same.id)

        person = BirthdayPerson.objects.create(
            family=self.family,
            name="Oma",
            birth_month=4,
            birth_day=8,
            birth_year=1950,
            created_by=self.owner,
        )
        person_occasion, person_created = get_or_create_birthday_occasion(
            family=self.family,
            person=person,
            occurrence_year=2027,
            created_by=self.owner,
        )
        self.assertTrue(person_created)
        self.assertNotEqual(member_occasion.id, person_occasion.id)
        self.assertEqual(BirthdayOccasion.objects.count(), 2)
        self.assertFalse(FamilyEvent.objects.exists())
        field_names = {field.name for field in BirthdayOccasion._meta.fields}
        self.assertTrue({"family", "membership", "person", "occurrence_year"} <= field_names)
        self.assertFalse({"birth_month", "birth_day", "birth_year"} & field_names)

        with self.assertRaises(ValidationError):
            BirthdayOccasion.objects.create(
                family=self.family,
                membership=self.target_member,
                occurrence_year=2027,
            )

    def test_cross_family_occasion_and_context_link_are_rejected(self):
        with self.assertRaises(ValidationError):
            BirthdayOccasion.objects.create(
                family=self.family,
                membership=self.other_member,
                occurrence_year=2027,
            )

        occasion, _ = get_or_create_birthday_occasion(
            family=self.family,
            membership=self.target_member,
            occurrence_year=2027,
            created_by=self.owner,
        )
        foreign_task = Task.objects.create(
            family=self.other_family,
            title="Foreign secret",
            created_by=self.other_user,
        )
        with self.assertRaises(ContextObjectUnavailable):
            create_context_link(
                user=self.owner,
                family=self.family,
                source_type="birthday_occasion",
                source_id=occasion.id,
                context_type="task",
                context_id=foreign_task.id,
                relation_key="birthday.gift_task",
            )
        self.assertFalse(ContextLink.objects.exists())

    def test_context_link_rechecks_surprise_acl_and_hides_own_occasion(self):
        occasion, _ = get_or_create_birthday_occasion(
            family=self.family,
            membership=self.target_member,
            occurrence_year=2027,
            created_by=self.owner,
        )
        task = Task.objects.create(
            family=self.family,
            title="Secret gift",
            created_by=self.owner,
            hidden_from_user=self.viewer,
        )
        link, created = create_context_link(
            user=self.owner,
            family=self.family,
            source_type="birthday_occasion",
            source_id=occasion.id,
            context_type="task",
            context_id=task.id,
            relation_key="birthday.gift_task",
        )
        self.assertTrue(created)

        self.assertEqual(
            list_context_links(
                user=self.viewer,
                family=self.family,
                anchor_type="birthday_occasion",
                anchor_id=occasion.id,
            ),
            [],
        )
        self.assertTrue(ContextLink.objects.filter(pk=link.id).exists())
        with self.assertRaises(ContextObjectUnavailable):
            list_context_links(
                user=self.target,
                family=self.family,
                anchor_type="birthday_occasion",
                anchor_id=occasion.id,
            )

    def test_gift_plan_api_dual_writes_context_links_but_keeps_legacy_uuid(self):
        key = f"member:{self.target_member.id}"
        for action in ("task", "shopping", "task", "shopping"):
            response = self.client.post(
                "/api/birthday-gift-plans/",
                {
                    "family": str(self.family.id),
                    "birthday_key": key,
                    "idea_text": "Geheimes Fahrrad",
                    "action": action,
                },
                format="json",
            )
            self.assertEqual(response.status_code, 200, response.data)

        plan = BirthdayGiftPlan.objects.get(family=self.family, membership=self.target_member)
        occasion = BirthdayOccasion.objects.get(
            family=self.family,
            membership=self.target_member,
            occurrence_year=plan.occurrence_year,
        )
        task = Task.objects.get(pk=plan.linked_task_id)
        item = ShoppingItem.objects.get(pk=plan.linked_shopping_item_id)
        self.assertEqual(task.birthday_context, plan.id)
        self.assertEqual(item.birthday_context, plan.id)
        self.assertEqual(Task.objects.count(), 1)
        self.assertEqual(ShoppingItem.objects.count(), 1)
        links = ContextLink.objects.filter(source_type="birthday_occasion", source_id=occasion.id)
        self.assertEqual(links.count(), 2)
        self.assertEqual(
            set(links.values_list("relation_key", flat=True)),
            {"birthday.gift_task", "birthday.shopping_item"},
        )

    def test_gift_plan_backfill_is_idempotent_and_preserves_visibility_fields(self):
        plan = BirthdayGiftPlan.objects.create(
            family=self.family,
            membership=self.target_member,
            occurrence_year=2030,
            status="planned",
        )
        task = Task.objects.create(
            family=self.family,
            title="Legacy gift",
            created_by=self.owner,
            birthday_context=plan.id,
            hidden_from_user=self.target,
        )
        shopping_list = ShoppingList.objects.create(family=self.family, name="Legacy gifts")
        item = ShoppingItem.objects.create(
            shopping_list=shopping_list,
            name="Legacy present",
            added_by=self.owner,
            birthday_context=plan.id,
            hidden_from_user=self.target,
        )
        plan.linked_task = task
        plan.linked_shopping_item = item
        plan.save(update_fields=["linked_task", "linked_shopping_item", "updated_at"])

        migration = importlib.import_module("family.migrations.0215_birthday_occasion_context")
        migration.backfill_birthday_occasions(django_apps, None)
        migration.backfill_birthday_occasions(django_apps, None)

        occasion = BirthdayOccasion.objects.get(
            family=self.family,
            membership=self.target_member,
            occurrence_year=2030,
        )
        links = ContextLink.objects.filter(source_type="birthday_occasion", source_id=occasion.id)
        self.assertEqual(links.count(), 2)
        task.refresh_from_db()
        item.refresh_from_db()
        self.assertEqual(task.hidden_from_user_id, self.target.id)
        self.assertEqual(item.hidden_from_user_id, self.target.id)
        self.assertEqual(task.birthday_context, plan.id)
        self.assertEqual(item.birthday_context, plan.id)
