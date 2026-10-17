from datetime import datetime, timedelta, timezone as utc

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from icalendar import Calendar
from rest_framework.test import APIClient

from .models import Family, FamilyEvent, Membership


@override_settings(APP_URL='https://calendar.example.test', AUTH_ABUSE_HMAC_KEY='calendar-member-scope-tests', DEBUG=True)
class CalendarSubscriptionMemberScopeTests(TestCase):
    def setUp(self):
        self.owner_user = get_user_model().objects.create_user('scope-owner', password='calendar-test-password')
        self.child_user = get_user_model().objects.create_user('scope-child-user')
        self.family = Family.objects.create(name='Scope family', slug='calendar-member-scope', timezone='Europe/Berlin')
        self.owner = Membership.objects.create(family=self.family, user=self.owner_user, role=Membership.Role.OWNER, display_name='Alex')
        self.child = Membership.objects.create(family=self.family, user=self.child_user, role=Membership.Role.CHILD, display_name='Emma')
        start = datetime(2026, 10, 20, 15, 0, tzinfo=utc.utc)
        self.owner_event = FamilyEvent.objects.create(
            family=self.family, type='calendar.event', title='Owner event',
            starts_at=start, ends_at=start + timedelta(hours=1), is_family_event=False,
        )
        self.owner_event.participants.add(self.owner)
        self.child_event = FamilyEvent.objects.create(
            family=self.family, type='calendar.event', title='Child event',
            starts_at=start + timedelta(days=1), ends_at=start + timedelta(days=1, hours=1), is_family_event=False,
        )
        self.child_event.participants.add(self.child)

        self.client = APIClient()
        login = self.client.post('/api/auth/login/', {'username': self.owner_user.username, 'password': 'calendar-test-password'}, format='json')
        self.assertEqual(login.status_code, 200, login.data)
        self.path = f'/api/calendar-subscriptions/{self.family.pk}/'
        created = self.client.post(self.path, {'name': 'Owner iPhone', 'detail_level': 'title'}, format='json')
        self.assertEqual(created.status_code, 201, created.data)
        self.grant = created.data
        self.detail = self.path + self.grant['id'] + '/'
        self.public = APIClient()

    def member_feed(self, member):
        return f"/calendar-feed/{self.grant['password']}/member/{member.pk}.ics"

    @staticmethod
    def titles(response):
        return {str(event['SUMMARY']) for event in Calendar.from_ical(response.content).walk('VEVENT')}

    def test_unselected_child_feed_is_empty_until_link_scope_includes_child(self):
        owner_feed = self.public.get(self.member_feed(self.owner))
        self.assertEqual(owner_feed.status_code, 200)
        self.assertEqual(self.titles(owner_feed), {'Owner event'})

        child_feed = self.public.get(self.member_feed(self.child))
        self.assertEqual(child_feed.status_code, 200)
        self.assertEqual(self.titles(child_feed), set())

        scoped = self.client.patch(self.detail, {'included_member_ids': [str(self.child.pk)]}, format='json')
        self.assertEqual(scoped.status_code, 200, scoped.data)
        self.assertEqual(scoped.data['included_member_ids'], [str(self.child.pk)])

        selected_child_feed = self.public.get(self.member_feed(self.child))
        self.assertEqual(selected_child_feed.status_code, 200)
        self.assertEqual(self.titles(selected_child_feed), {'Child event'})

    def test_member_feed_never_expands_scope_to_unselected_adult(self):
        adult_user = get_user_model().objects.create_user('scope-adult-user')
        adult = Membership.objects.create(family=self.family, user=adult_user, role=Membership.Role.ADULT, display_name='Morgan')
        adult_event = FamilyEvent.objects.create(
            family=self.family, type='calendar.event', title='Adult event',
            starts_at=datetime(2026, 10, 22, 15, 0, tzinfo=utc.utc),
            ends_at=datetime(2026, 10, 22, 16, 0, tzinfo=utc.utc), is_family_event=False,
        )
        adult_event.participants.add(adult)

        response = self.public.get(self.member_feed(adult))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.titles(response), set())
