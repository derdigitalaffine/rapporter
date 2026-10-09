import os
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils.text import slugify
from family.models import Family, Membership, TaskList, ShoppingList, Routine, AutomationRule


class Command(BaseCommand):
    help = "Idempotently bootstrap FamilyOS global administration and the first household"

    def _user(self, username, password, email="", *, superadmin=False):
        User = get_user_model()
        user, created = User.objects.get_or_create(
            username=username,
            defaults={"email": email, "is_staff": superadmin, "is_superuser": superadmin},
        )
        if created:
            user.set_password(password)
        if email and user.email != email:
            user.email = email
        if superadmin:
            user.is_staff = True
            user.is_superuser = True
        user.save()
        return user

    def handle(self, *args, **options):
        super_username = os.getenv("DJANGO_SUPERUSER_USERNAME")
        super_password = os.getenv("DJANGO_SUPERUSER_PASSWORD")
        super_email = os.getenv("DJANGO_SUPERUSER_EMAIL", "")
        if not super_username or not super_password:
            self.stdout.write("Bootstrap skipped: no global superadmin credentials configured")
            return

        superadmin = self._user(super_username, super_password, super_email, superadmin=True)
        family_name = os.getenv("INITIAL_FAMILY_NAME", "Meine Familie")
        locale = os.getenv("INITIAL_LOCALE", "de")
        family_timezone = os.getenv("TIME_ZONE", "Europe/Berlin")
        family, family_created = Family.objects.get_or_create(
            slug=slugify(family_name)[:120] or "meine-familie",
            defaults={"name": family_name, "locale": locale, "timezone": family_timezone},
        )
        if not family_created:
            changed = False
            for field, value in [("name", family_name), ("locale", locale), ("timezone", family_timezone)]:
                if getattr(family, field) != value:
                    setattr(family, field, value)
                    changed = True
            if changed:
                family.save(update_fields=["name", "locale", "timezone", "updated_at"])

        owner_username = os.getenv("INITIAL_OWNER_USERNAME", "").strip()
        owner_password = os.getenv("INITIAL_OWNER_PASSWORD", "").strip()
        owner_email = os.getenv("INITIAL_OWNER_EMAIL", "").strip()
        owner = None
        if owner_username and owner_password:
            if owner_username == super_username:
                raise ValueError("INITIAL_OWNER_USERNAME must differ from DJANGO_SUPERUSER_USERNAME")
            owner = self._user(owner_username, owner_password, owner_email)
            Membership.objects.update_or_create(
                family=family,
                user=owner,
                defaults={"role": Membership.Role.OWNER, "display_name": owner_username},
            )
            # New installations keep the global superadmin outside all tenants. On an
            # upgraded installation we only remove a legacy membership once another
            # owner exists, avoiding an orphaned household during migration.
            Membership.objects.filter(family=family, user=superadmin).delete()
        elif not Membership.objects.filter(family=family, role=Membership.Role.OWNER).exists():
            self.stderr.write(
                "No INITIAL_OWNER_* credentials configured and the first family has no owner. "
                "Run setup again or create an owner through the Superadmin UI."
            )

        TaskList.objects.get_or_create(family=family, name="Allgemein", defaults={"icon": "list-check"})
        TaskList.objects.get_or_create(family=family, name="Haushalt", defaults={"icon": "house"})
        ShoppingList.objects.get_or_create(family=family, name="Einkauf", defaults={"icon": "cart-shopping"})
        AutomationRule.objects.get_or_create(
            family=family,
            name="Müll rausstellen",
            defaults={
                "created_by": owner,
                "icon": "trash-can",
                "enabled": True,
                "trigger_type": AutomationRule.Trigger.WASTE_TOMORROW,
                "trigger_config": {},
                "action_type": AutomationRule.Action.TASK_CREATE,
                "action_config": {"title": "{event_title} rausstellen", "priority": "normal"},
            },
        )
        for name, days, icon in [
            ("Bad putzen", 7, "sparkles"),
            ("Bettwäsche wechseln", 14, "bed"),
            ("Kühlschrank reinigen", 30, "snowflake"),
            ("Wasserfilter wechseln", 30, "droplets"),
        ]:
            Routine.objects.get_or_create(family=family, name=name, defaults={"suggested_interval_days": days, "icon": icon})
        self.stdout.write(self.style.SUCCESS("FamilyOS bootstrap complete"))
