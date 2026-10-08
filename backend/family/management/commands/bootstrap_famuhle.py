import os
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from family.models import Family, Membership, ShoppingList, Routine


class Command(BaseCommand):
    help = "Idempotently bootstrap the first fam-uh-le household"

    def handle(self, *args, **options):
        username = os.getenv("DJANGO_SUPERUSER_USERNAME")
        password = os.getenv("DJANGO_SUPERUSER_PASSWORD")
        email = os.getenv("DJANGO_SUPERUSER_EMAIL", "")
        if not username or not password:
            self.stdout.write("Bootstrap skipped: no initial admin credentials configured")
            return

        User = get_user_model()
        user, created = User.objects.get_or_create(
            username=username,
            defaults={"email": email, "is_staff": True, "is_superuser": True},
        )
        if created:
            user.set_password(password)
        elif email and user.email != email:
            user.email = email
        user.is_staff = True
        user.is_superuser = True
        user.save()

        family_name = os.getenv("INITIAL_FAMILY_NAME", "Meine Familie")
        locale = os.getenv("INITIAL_LOCALE", "de")
        timezone = os.getenv("TIME_ZONE", "Europe/Berlin")
        family, family_created = Family.objects.get_or_create(
            slug="meine-familie",
            defaults={"name": family_name, "locale": locale, "timezone": timezone},
        )
        if family_created is False:
            changed = False
            if family.name != family_name:
                family.name = family_name
                changed = True
            if family.locale != locale:
                family.locale = locale
                changed = True
            if family.timezone != timezone:
                family.timezone = timezone
                changed = True
            if changed:
                family.save(update_fields=["name", "locale", "timezone", "updated_at"])

        Membership.objects.get_or_create(
            family=family,
            user=user,
            defaults={"role": Membership.Role.OWNER, "display_name": username},
        )
        ShoppingList.objects.get_or_create(family=family, name="Einkauf")
        for name, days, icon in [
            ("Bad putzen", 7, "sparkles"),
            ("Bettwäsche wechseln", 14, "bed"),
            ("Kühlschrank reinigen", 30, "snowflake"),
            ("Wasserfilter wechseln", 30, "droplets"),
        ]:
            Routine.objects.get_or_create(
                family=family,
                name=name,
                defaults={"suggested_interval_days": days, "icon": icon},
            )
        self.stdout.write(self.style.SUCCESS("fam-uh-le bootstrap complete"))
