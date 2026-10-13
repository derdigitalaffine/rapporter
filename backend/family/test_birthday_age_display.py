from datetime import date, datetime, timezone as utc
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from .birthday_age import set_age_enabled
from .birthdays import calendar_projection, project, run_birthday_reminders
from .models import BirthdayPerson, Family, Membership, UserProfile


class BirthdayAgeDisplayTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user(username="age-owner")
        self.mia = User.objects.create_user(username="age-mia")
        self.family = Family.objects.create(name="Age Family", slug="age-family", locale="de")
        self.owner_member = Membership.objects.create(family=self.family, user=self.owner, role="owner")
        self.mia_member = Membership.objects.create(
            family=self.family, user=self.mia, role="adult", display_name="Mia", birthday_visibility="full_date"
        )
        UserProfile.objects.create(user=self.mia, birth_month=3, birth_day=12, birth_year=2016)
        self.client = APIClient()
        self.client.force_authenticate(self.owner)

    def test_age_defaults_on_but_never_bypasses_birthday_privacy(self):
        row = project(self.family, self.owner, date(2026, 3, 12))[0]
        self.assertEqual(row["turning_age"], 10)
        self.assertTrue(row["show_birthday_age"])

        self.mia_member.birthday_visibility = Membership.BirthdayVisibility.DAY_MONTH
        self.mia_member.save(update_fields=["birthday_visibility"])
        row = project(self.family, self.owner, date(2026, 3, 12))[0]
        self.assertIsNone(row["birth_year"])
        self.assertIsNone(row["turning_age"])

        self.mia_member.birthday_visibility = Membership.BirthdayVisibility.HIDDEN
        self.mia_member.save(update_fields=["birthday_visibility"])
        self.assertEqual(project(self.family, self.owner, date(2026, 3, 12)), [])

    def test_age_can_be_disabled_and_calendar_uses_same_projection(self):
        key = f"member:{self.mia_member.id}"
        set_age_enabled(self.family, key, False)
        row = project(self.family, self.owner, date(2026, 3, 12))[0]
        self.assertIsNone(row["turning_age"])
        calendar = calendar_projection(self.family, self.owner, date(2026, 1, 1), date(2026, 12, 31))
        self.assertNotIn("wird 10", calendar[0]["title"])
        self.assertIsNone(calendar[0]["payload"]["turning_age"])

        set_age_enabled(self.family, key, True)
        calendar = calendar_projection(self.family, self.owner, date(2026, 1, 1), date(2026, 12, 31))
        self.assertIn("wird 10", calendar[0]["title"])
        self.assertEqual(calendar[0]["payload"]["turning_age"], 10)

    def test_profile_and_external_birthday_settings_persist(self):
        response = self.client.patch(
            f"/api/profile/?family={self.family.id}",
            {"family": str(self.family.id), "show_birthday_age": False},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertFalse(response.data["show_birthday_age"])

        response = self.client.post(
            "/api/birthday-people/",
            {
                "family": str(self.family.id),
                "name": "Oma",
                "birth_month": 4,
                "birth_day": 2,
                "birth_year": 1950,
                "show_birthday_age": False,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertFalse(response.data["show_birthday_age"])
        person = BirthdayPerson.objects.get(name="Oma")
        external = next(row for row in project(self.family, self.owner, date(2026, 1, 1)) if row["id"] == str(person.id))
        self.assertIsNone(external["turning_age"])

    @patch("family.birthdays.send_user_push", return_value={"sent": 1, "errors": 0})
    def test_reminders_include_age_only_when_enabled(self, push):
        run_birthday_reminders(datetime(2027, 3, 12, 9, tzinfo=utc.utc))
        bodies = [call.args[2] for call in push.call_args_list]
        self.assertTrue(any("wird 11" in body for body in bodies))

        push.reset_mock()
        from .models import BirthdayReminder
        BirthdayReminder.objects.all().delete()
        set_age_enabled(self.family, f"member:{self.mia_member.id}", False)
        run_birthday_reminders(datetime(2028, 3, 12, 9, tzinfo=utc.utc))
        bodies = [call.args[2] for call in push.call_args_list]
        self.assertTrue(bodies)
        self.assertTrue(all("wird 12" not in body for body in bodies))
