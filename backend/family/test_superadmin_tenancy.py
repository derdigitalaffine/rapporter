from datetime import timedelta
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient
from .models import Family, FamilyInvitation, Membership, Task, TaskList

class SuperAdminTenantTests(TestCase):
    def setUp(self):
        User=get_user_model();self.superadmin=User.objects.create_superuser("root","root@example.test","strong-password");self.normal=User.objects.create_user("normal",password="strong-password");self.client=APIClient()
    def test_only_superadmin_can_manage_tenants_and_owner_invites(self):
        self.client.force_authenticate(self.normal);self.assertEqual(self.client.get("/api/superadmin/families/").status_code,403);self.client.force_authenticate(self.superadmin)
        response=self.client.post("/api/superadmin/families/",{"name":"Familie Zwei","owner_email":"owner2@example.test","owner_name":"Owner Zwei","locale":"de","timezone":"Europe/Berlin"},format="json");self.assertEqual(response.status_code,201);family=Family.objects.get(name="Familie Zwei");self.assertFalse(Membership.objects.filter(family=family,user=self.superadmin).exists());invite=FamilyInvitation.objects.get(token=response.data["invite_token"]);self.assertEqual(invite.role,Membership.Role.OWNER);self.assertTrue(invite.is_active)
    def test_two_families_are_isolated(self):
        User=get_user_model();owner_a=User.objects.create_user("owner-a",password="strong-password");owner_b=User.objects.create_user("owner-b",password="strong-password");family_a=Family.objects.create(name="A",slug="a");family_b=Family.objects.create(name="B",slug="b");Membership.objects.create(family=family_a,user=owner_a,role=Membership.Role.OWNER);Membership.objects.create(family=family_b,user=owner_b,role=Membership.Role.OWNER);task_list=TaskList.objects.create(family=family_a,name="Privat");Task.objects.create(family=family_a,task_list=task_list,title="Nur A",created_by=owner_a);self.client.force_authenticate(owner_b);families=self.client.get("/api/families/");self.assertEqual(families.status_code,200);self.assertEqual([row["name"] for row in families.data["results"]],["B"]);tasks=self.client.get("/api/tasks/");self.assertEqual(tasks.status_code,200);self.assertEqual(tasks.data["results"],[])
    def test_suspended_family_invalidates_invites_and_disappears_from_app_scope(self):
        family=Family.objects.create(name="Paused",slug="paused");Membership.objects.create(family=family,user=self.normal,role=Membership.Role.OWNER);invite=FamilyInvitation.objects.create(family=family,role=Membership.Role.OWNER,invited_by=self.superadmin,expires_at=timezone.now()+timedelta(days=7));self.assertTrue(invite.is_active);family.status=Family.Status.SUSPENDED;family.save(update_fields=["status"]);invite.refresh_from_db();self.assertFalse(invite.is_active);self.client.force_authenticate(self.normal);families=self.client.get("/api/families/");self.assertEqual(families.status_code,200);self.assertEqual(families.data["results"],[]);self.assertEqual(self.client.get("/api/tasks/").status_code,403);self.assertEqual(self.client.get("/api/auth/session/").status_code,200)
    def test_setup_bootstraps_separate_global_admin_and_family_owner(self):
        env={"DJANGO_SUPERUSER_USERNAME":"global-admin","DJANGO_SUPERUSER_PASSWORD":"global-password-123","DJANGO_SUPERUSER_EMAIL":"global@example.test","INITIAL_OWNER_USERNAME":"family-owner","INITIAL_OWNER_PASSWORD":"owner-password-123","INITIAL_OWNER_EMAIL":"owner@example.test","INITIAL_FAMILY_NAME":"Startfamilie","INITIAL_LOCALE":"de","TIME_ZONE":"Europe/Berlin"}
        with patch.dict("os.environ",env,clear=False):call_command("bootstrap_famuhle")
        User=get_user_model();global_admin=User.objects.get(username="global-admin");owner=User.objects.get(username="family-owner");family=Family.objects.get(slug="meine-familie");self.assertTrue(global_admin.is_superuser);self.assertFalse(Membership.objects.filter(user=global_admin).exists());self.assertTrue(Membership.objects.filter(family=family,user=owner,role=Membership.Role.OWNER).exists())
