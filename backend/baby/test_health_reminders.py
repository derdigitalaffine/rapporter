import uuid
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from family.family_relationship_models import FamilyRelationship
from family.models import Family, FamilyEvent, Membership, Task
from .models import BabyProfile, CareCircleAccess, ChildHealthRecord, FamilyModuleSetting, PregnancyJourney
from .reference_service import DEFAULT_SOURCE_KEY, create_reference_draft, publish_reference_package


class HealthReminderTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="reminder-parent")
        self.helper = User.objects.create_user(username="reminder-helper")
        self.admin = User.objects.create_superuser(username="reminder-admin", password="test-only-password")
        self.family = Family.objects.create(name="Reminder family", slug="health-reminders")
        self.member = Membership.objects.create(user=self.user, family=self.family, role="adult")
        self.helper_member = Membership.objects.create(user=self.helper, family=self.family, role="adult")
        FamilyModuleSetting.objects.create(family=self.family, module_key="pregnancy_baby", enabled=True)
        self.child_member = Membership.objects.create(user=User.objects.create_user(username="reminder-child"), family=self.family, role="child")
        self.baby = BabyProfile.objects.create(family=self.family, membership=self.child_member, display_name="Private child",
                                               birth_date=timezone.localdate()-timedelta(days=40))
        self.custody = FamilyRelationship.objects.create(family=self.family, child_membership=self.child_member,
            related_membership=self.member, kind="parent", has_custody=True, status="active")
        # Synthetic source, deliberately not represented as STIKO content.
        self.package = create_reference_draft(self.admin, source_key=DEFAULT_SOURCE_KEY, source_title="Synthetic test reference",
            source_version="test-1", payload={"schema_version":1,"vaccinations":[
                {"key":"test-group","display":{"de":"Testimpfung","en":"Test vaccination"},"doses":[
                    {"sequence":1,"age_window":{"start_day":42,"end_day":90}},
                    {"sequence":2,"age_window":{"start_day":100,"end_day":150}},
                ]}
            ]})
        publish_reference_package(self.admin, self.package.id)
        self.package.refresh_from_db()
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.path = f"/api/baby/profiles/{self.baby.id}/health/reminders/"
        self.due = timezone.now()+timedelta(days=3)

    def payload(self, sequences=(1,2), **changes):
        return {"remind_at":self.due.isoformat(),"entries":[
            {"key":f"vaccination:test-group:{sequence}","expected_version":0,"reference_checksum":self.package.checksum}
            for sequence in sequences
        ], **changes}

    def test_explicit_selection_creates_one_generic_task_and_retry_is_idempotent(self):
        self.assertEqual(Task.objects.count(),0)
        result = self.client.post(self.path,self.payload(),format="json")
        self.assertEqual(result.status_code,200,result.data)
        repeated = self.client.post(self.path,self.payload(),format="json")
        self.assertEqual(repeated.status_code,200,repeated.data)
        self.assertEqual(Task.objects.count(),1)
        task = Task.objects.get()
        self.assertEqual(task.title,"Termin vereinbaren")
        self.assertEqual(task.notes,"")
        self.assertEqual(task.source,"manual")
        self.assertEqual(task.assignee,self.user)
        self.assertEqual(task.due_at,self.due)
        self.assertEqual(ChildHealthRecord.objects.filter(reminder_task=task).count(),2)
        self.assertFalse(ChildHealthRecord.objects.exclude(state="unknown").exists())
        self.assertFalse(FamilyEvent.objects.exists())
        payload = str(self.client.get(f"/api/tasks/?family={self.family.id}").data)
        for secret in [self.baby.display_name,str(self.baby.id),"Testimpfung","test-group",self.package.checksum]:
            self.assertNotIn(secret,payload)

    def test_get_has_source_version_and_reminder_link_without_mutation(self):
        path=f"/api/baby/profiles/{self.baby.id}/health/"
        response=self.client.get(path)
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.data["vaccination_reference"]["version"],"test-1")
        self.assertTrue(any(row["kind"]=="exam" for row in response.data["items"]))
        self.assertFalse(Task.objects.exists())
        self.client.post(self.path,self.payload((1,)),format="json")
        response=self.client.get(path)
        row=next(row for row in response.data["items"] if row["key"]=="vaccination:test-group:1")
        self.assertEqual(row["reminder"]["task"],str(Task.objects.get().id))
        self.assertFalse(row["reminder"]["completed"])

    def test_invalid_selection_is_atomic_and_no_past_or_duplicate_reminders(self):
        for payload in [self.payload((1,9)),self.payload((1,1)),self.payload(remind_at=(timezone.now()-timedelta(days=1)).isoformat()),self.payload(entries=[])]:
            response=self.client.post(self.path,payload,format="json")
            self.assertEqual(response.status_code,400,response.data)
            self.assertFalse(Task.objects.exists())
            self.assertFalse(ChildHealthRecord.objects.exists())

    def test_changed_reference_or_record_returns_conflict(self):
        payload=self.payload((1,))
        payload["entries"][0]["reference_checksum"]="0"*64
        self.assertEqual(self.client.post(self.path,payload,format="json").status_code,409)
        payload=self.payload((1,))
        payload["entries"][0]["expected_version"]=1
        self.assertEqual(self.client.post(self.path,payload,format="json").status_code,409)
        self.assertFalse(Task.objects.exists())

    def test_existing_task_cannot_be_duplicated_or_silently_rescheduled(self):
        self.client.post(self.path,self.payload((1,)),format="json")
        payload=self.payload((1,))
        payload["entries"][0]["expected_version"]=1
        payload["remind_at"]=(self.due+timedelta(days=1)).isoformat()
        self.assertEqual(self.client.post(self.path,payload,format="json").status_code,409)
        self.assertEqual(Task.objects.count(),1)
        self.assertEqual(Task.objects.get().due_at,self.due)

    def test_done_planned_and_historical_are_not_automatically_reminded(self):
        for state in ["done","planned"]:
            row=ChildHealthRecord.objects.create(baby=self.baby,key="vaccination:test-group:1",kind="vaccination",title="Test",state=state)
            payload=self.payload((1,))
            payload["entries"][0]["expected_version"]=1
            self.assertEqual(self.client.post(self.path,payload,format="json").status_code,400)
            row.delete()
        self.baby.birth_date=timezone.localdate()-timedelta(days=200)
        self.baby.save()
        self.assertEqual(self.client.post(self.path,self.payload(),format="json").status_code,400)
        self.assertFalse(Task.objects.exists())

    def test_delegation_and_revocation_are_enforced_without_pregnancy_leak(self):
        self.client.force_authenticate(self.helper)
        self.assertEqual(self.client.post(self.path,self.payload(),format="json").status_code,403)
        grant=CareCircleAccess.objects.create(family=self.family,baby=self.baby,membership=self.helper_member,can_view_growth_development=True)
        self.assertEqual(self.client.post(self.path,self.payload(),format="json").status_code,200)
        grant.delete()
        self.assertEqual(self.client.post(self.path,self.payload(),format="json").status_code,403)
        self.assertEqual(Task.objects.count(),1)

    def test_cross_family_and_other_child_are_denied(self):
        outsider=get_user_model().objects.create_user(username="outsider-reminder")
        other_family=Family.objects.create(name="Other",slug="other-reminder")
        Membership.objects.create(user=outsider,family=other_family,role="owner")
        self.client.force_authenticate(outsider)
        self.assertEqual(self.client.post(self.path,self.payload(),format="json").status_code,403)
        self.assertFalse(Task.objects.exists())

    def test_widget_summary_requires_separate_pregnancy_access_and_active_journey(self):
        pregnancy=PregnancyJourney.objects.create(family=self.family,expected_due_date=timezone.localdate()+timedelta(days=70),notes="Secret pregnancy note")
        path=f"/api/baby/module/?family={self.family.id}"
        self.assertIsNone(self.client.get(path).data["active_pregnancy"])
        grant=CareCircleAccess.objects.create(family=self.family,membership=self.member,can_view_pregnancy=True)
        summary=self.client.get(path).data["active_pregnancy"]
        self.assertEqual(set(summary),{"expected_due_date","progress"})
        self.assertNotIn("Secret",str(summary))
        pregnancy.status="archived"
        pregnancy.save()
        self.assertIsNone(self.client.get(path).data["active_pregnancy"])
        pregnancy.status="active"
        pregnancy.save()
        grant.delete()
        self.assertIsNone(self.client.get(path).data["active_pregnancy"])
