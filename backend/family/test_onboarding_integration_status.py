from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from .models import Family, IntegrationSource, Membership


class OnboardingIntegrationStatusTests(TestCase):
    def setUp(self):
        User=get_user_model()
        self.user=User.objects.create_user(username="onboarding-owner",password="test-pass-123")
        self.other=User.objects.create_user(username="other-onboarding-owner",password="test-pass-123")
        self.family=Family.objects.create(name="Onboarding Family",slug="onboarding-family")
        self.other_family=Family.objects.create(name="Other Onboarding Family",slug="other-onboarding-family")
        Membership.objects.create(family=self.family,user=self.user,role=Membership.Role.OWNER)
        Membership.objects.create(family=self.other_family,user=self.other,role=Membership.Role.OWNER)
        self.client=APIClient();self.client.force_authenticate(self.user)

    def test_dashboard_counts_only_active_family_integrations(self):
        IntegrationSource.objects.create(family=self.family,name="Enabled",kind=IntegrationSource.Kind.WEATHER,enabled=True)
        IntegrationSource.objects.create(family=self.family,name="Disabled",kind=IntegrationSource.Kind.ICS,enabled=False)
        IntegrationSource.objects.create(family=self.other_family,name="Other",kind=IntegrationSource.Kind.WEATHER,enabled=True)

        response=self.client.get(f"/api/dashboard/?family={self.family.id}")

        self.assertEqual(response.status_code,200)
        self.assertEqual(response.data["integration_count"],2)
        self.assertEqual(response.data["enabled_integration_count"],1)

    def test_disabled_integrations_do_not_complete_onboarding_status(self):
        IntegrationSource.objects.create(family=self.family,name="Disabled",kind=IntegrationSource.Kind.WEATHER,enabled=False)

        response=self.client.get(f"/api/dashboard/?family={self.family.id}")

        self.assertEqual(response.status_code,200)
        self.assertEqual(response.data["integration_count"],1)
        self.assertEqual(response.data["enabled_integration_count"],0)

    def test_other_family_integration_does_not_leak_into_status(self):
        IntegrationSource.objects.create(family=self.other_family,name="Other",kind=IntegrationSource.Kind.WEATHER,enabled=True)

        response=self.client.get(f"/api/dashboard/?family={self.family.id}")

        self.assertEqual(response.status_code,200)
        self.assertEqual(response.data["integration_count"],0)
        self.assertEqual(response.data["enabled_integration_count"],0)
