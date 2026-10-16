from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from .models import BoardPost, Family, Membership, ShoppingItem, ShoppingList
from .shopping_models import ShoppingListAccess


class TodayOverviewTests(TestCase):
    def setUp(self):
        users = get_user_model()
        self.user = users.objects.create_user(username='overview-owner')
        self.other = users.objects.create_user(username='overview-other')
        self.family = Family.objects.create(name='Overview', slug='overview')
        self.foreign = Family.objects.create(name='Foreign', slug='overview-foreign')
        self.member = Membership.objects.create(family=self.family, user=self.user, role='owner')
        Membership.objects.create(family=self.family, user=self.other, role='adult')
        Membership.objects.create(family=self.foreign, user=self.other, role='owner')
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.url = f'/api/dashboard/?family={self.family.id}'
        self.weather = patch('family.dashboard_weather_views.weather_payload', return_value={})
        self.weather.start()
        self.addCleanup(self.weather.stop)

    def shopping_list(self, *, family=None, visibility=None, author=None, archived=False):
        row = ShoppingList.objects.create(family=family or self.family, name='List', archived=archived)
        if visibility:
            ShoppingListAccess.objects.create(shopping_list=row, visibility=visibility, created_by=author or self.other)
        ShoppingItem.objects.create(shopping_list=row, name='Item')
        return row

    def test_counts_all_visible_lists_not_only_dashboard_preview(self):
        for _ in range(10):
            self.shopping_list()
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data['shopping_lists']), 8)
        self.assertEqual(response.data['overview'], {'shopping_open_count': 10, 'pin_count': 0})

    def test_shopping_count_respects_acl_archival_checked_and_surprise_privacy(self):
        shared = self.shopping_list()
        self.shopping_list(family=self.foreign)
        self.shopping_list(archived=True)
        self.shopping_list(visibility='private')
        self.shopping_list(visibility='private', author=self.user)
        selected = self.shopping_list(visibility='selected')
        selected.access_settings.visible_members.add(self.member)
        self.shopping_list(visibility='selected')
        ShoppingItem.objects.create(shopping_list=shared, name='Already bought', checked=True)
        ShoppingItem.objects.create(shopping_list=shared, name='Surprise', hidden_from_user=self.user)
        response = self.client.get(self.url)
        self.assertEqual(response.data['overview']['shopping_open_count'], 3)
        selected.access_settings.visible_members.remove(self.member)
        self.assertEqual(self.client.get(self.url).data['overview']['shopping_open_count'], 2)

    def test_pin_count_uses_same_authorized_shell_scope_and_revocation(self):
        BoardPost.objects.create(family=self.family, author=self.other, text='Shared')
        BoardPost.objects.create(family=self.family, author=self.user, visibility='private')
        BoardPost.objects.create(family=self.family, author=self.other, visibility='private')
        BoardPost.objects.create(family=self.foreign, author=self.other)
        selected = BoardPost.objects.create(family=self.family, author=self.other, visibility='selected')
        selected.visible_to_memberships.add(self.member)
        BoardPost.objects.create(family=self.family, author=self.other, visibility='selected')
        response = self.client.get(self.url)
        self.assertEqual(response.data['overview']['pin_count'], 3)
        self.assertEqual(set(response.data['overview']), {'shopping_open_count', 'pin_count'})
        selected.visible_to_memberships.clear()
        self.assertEqual(self.client.get(self.url).data['overview']['pin_count'], 2)

    def test_family_guessed_id_and_removed_membership_do_not_expose_counts(self):
        self.assertEqual(self.client.get(f'/api/dashboard/?family={self.foreign.id}').status_code, 403)
        self.member.delete()
        self.assertEqual(self.client.get(self.url).status_code, 403)

    def test_empty_authorized_sources_are_real_zeroes(self):
        self.assertEqual(self.client.get(self.url).data['overview'], {'shopping_open_count': 0, 'pin_count': 0})
