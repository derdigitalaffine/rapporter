from datetime import datetime, timedelta, timezone as dt_timezone
from io import StringIO
from uuid import uuid4
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.db import IntegrityError, transaction, connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APIClient
from entitlements.models import EntitlementCutover, EntitlementGrant, CapabilityDefinition
from family.models import Family, Membership, Task, Routine, RoutineLog, ShoppingList, ShoppingItem
from family.request_context import clear_current_actor
from .models import FamilyContributionEvent as Event, FamilyContributionDaily as Daily
from .services import record, recompute


class StatisticsTests(TestCase):
    def setUp(self):
        clear_current_actor()
        self.user = get_user_model().objects.create_user(username="alex")
        self.other = get_user_model().objects.create_user(username="sam")
        self.family = Family.objects.create(name="Family", slug="family")
        self.member = Membership.objects.create(family=self.family, user=self.user, role="owner", display_name="Alex")
        self.other_member = Membership.objects.create(family=self.family, user=self.other, role="adult", display_name="Sam")
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def tearDown(self):
        clear_current_actor()

    def read(self, suffix="", **params):
        return self.client.get(f"/api/statistics/{suffix}", {"family": str(self.family.id), **params})

    def emit(self, **extra):
        args = dict(family=self.family, domain="task", action="completed", entity_type="task", entity_id=uuid4(), actor=self.user, occurred_at=timezone.now(), idempotency_key=str(uuid4()), effort_minutes=20)
        args.update(extra)
        return record(**args)

    def cutover(self, capabilities=None):
        now = timezone.now()
        EntitlementCutover.objects.create(key="commercial-v1", cutover_at=now, applied_at=now, eligible_family_count=0)
        if capabilities is not None:
            EntitlementGrant.objects.create(family=self.family, origin="admin_grant", capability_set=capabilities)

    def test_record_dedupe_and_recompute(self):
        key = str(uuid4())
        self.assertEqual(self.emit(idempotency_key=key).pk, self.emit(idempotency_key=key).pk)
        self.assertEqual(Daily.objects.get().count, 1)
        recompute(self.family)
        recompute(self.family)
        row = Daily.objects.get()
        self.assertEqual((row.count, row.effort_minutes_sum, row.effort_coverage_count), (1, 20, 1))

    def test_no_content_contract_and_allowlist(self):
        self.assertFalse({f.name for f in Event._meta.fields} & {"title", "notes", "metadata", "payload", "location", "token", "secret"})
        with self.assertRaises(ValueError):
            self.emit(domain="messenger", action="sent")
        with self.assertRaises(TypeError):
            self.emit(title="Secret")
        with self.assertRaises(ValueError):
            self.emit(effort_minutes=True)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Event.objects.create(family=self.family, domain="baby", action="completed", entity_type="baby", occurred_at=timezone.now(), idempotency_key="invalid", source="ui")

    def test_premium_downgrade_stops_capture_and_read(self):
        self.emit()
        self.cutover()
        self.assertIsNone(self.emit())
        self.assertEqual(self.read().status_code, 403)
        self.assertEqual(self.read("tasks/").status_code, 403)
        self.assertEqual(Event.objects.count(), 1)
        EntitlementGrant.objects.create(family=self.family, origin="admin_grant", plan_key="premium")
        self.assertEqual(self.read().status_code, 200)

    def test_cross_family_suspended_and_invalid_ids(self):
        foreign = Family.objects.create(name="Foreign", slug="foreign")
        self.assertEqual(self.read(family=str(foreign.id)).status_code, 404)
        self.assertEqual(self.read(member=str(uuid4())).status_code, 404)
        self.assertEqual(self.read(family="bad").status_code, 400)
        self.family.status = "suspended"
        self.family.save()
        self.assertEqual(self.read().status_code, 404)

    def test_roles_owner_adult_teen_child_guest(self):
        self.emit()
        self.emit(actor=self.other)
        for role, members, completed, status in [("owner", 2, 2, 200), ("adult", 2, 2, 200), ("teen", 1, 2, 200), ("child", 1, 1, 200), ("guest", 0, 0, 403)]:
            self.member.role = role
            self.member.save()
            response = self.read()
            self.assertEqual(response.status_code, status)
            if status == 200:
                self.assertEqual(len(response.data["members"]), members)
                self.assertEqual(response.data["summary"]["completed"], completed)
                self.assertEqual(response.data["meta"]["can_compare_members"], role in {"owner", "adult"})
                if role == "teen":
                    self.assertNotIn(str(self.other_member.pk), str(self.read("tasks/").data))
                    self.assertEqual(self.read(member=str(self.other_member.pk)).status_code, 403)

    def test_domain_intersection_and_filter(self):
        self.emit()
        self.emit(domain="shopping", action="item_purchased", entity_type="shopping_item")
        self.cutover(["statistics", "todo"])
        CapabilityDefinition.objects.filter(key="shopping").update(deprecated=True)
        response = self.read()
        self.assertEqual(response.data["summary"]["completed"], 1)
        self.assertEqual(response.data["meta"]["available_domains"], ["task", "routine"])
        self.assertEqual(self.read("shopping/").status_code, 403)
        self.assertEqual(self.read(domain="shopping").status_code, 403)

    def test_task_actor_independent_of_assignee_retry_and_reopen(self):
        task = Task.objects.create(family=self.family, title="Private title never in stats", assignee=self.other, created_by=self.user, estimate_minutes=25)
        body = {"action_id": f"task:{task.pk}", "request_id": str(uuid4())}
        response = self.client.post("/api/actions/execute/", body, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.client.post("/api/actions/execute/", body, format="json")
        events = Event.objects.filter(entity_id=task.id, action="completed")
        self.assertEqual(events.count(), 1)
        self.assertEqual(events.get().actor_user_id, self.user.pk)
        self.assertEqual(events.get().effort_minutes, 25)
        self.assertNotIn(task.title, str(self.read("tasks/").data))
        self.client.post("/api/actions/execute/", {**body, "request_id": str(uuid4()), "operation": "reopen"}, format="json")
        self.assertEqual(Event.objects.filter(action="reopened").count(), 1)

    def test_routine_actor_retry_undo_and_no_note(self):
        routine = Routine.objects.create(family=self.family, name="Routine")
        key = str(uuid4())
        response = self.client.post(f"/api/routines/{routine.pk}/done/", {"request_id": key, "note": "Never expose note"}, format="json")
        self.assertEqual(response.status_code, 201)
        self.client.post(f"/api/routines/{routine.pk}/done/", {"request_id": key}, format="json")
        self.assertEqual(Event.objects.filter(domain="routine", action="completed").count(), 1)
        self.assertEqual(Event.objects.get(domain="routine", action="completed").actor_user_id, self.user.pk)
        self.assertNotIn("Never expose note", str(self.read("routines/").data))
        self.client.delete(f"/api/routines/{routine.pk}/logs/{response.data['id']}/")
        self.assertEqual(Event.objects.filter(domain="routine", action="completed").count(), 0)

    def test_shopping_purchase_actor_and_gift_exclusion(self):
        shopping = ShoppingList.objects.create(family=self.family)
        item = ShoppingItem.objects.create(shopping_list=shopping, name="Shopping secret", added_by=self.other)
        self.client.post(f"/api/shopping-items/{item.pk}/toggle/", {}, format="json")
        self.assertEqual(Event.objects.get(action="item_purchased").actor_user_id, self.user.pk)
        self.assertNotIn(item.name, str(self.read("shopping/").data))
        item.hidden_from_user = self.user
        item.save()
        self.assertFalse(Event.objects.filter(entity_id=item.pk).exists())
        hidden = Task.objects.create(family=self.family, title="Gift", hidden_from_user=self.other, completed_at=timezone.now())
        self.assertFalse(Event.objects.filter(entity_id=hidden.pk).exists())

    def test_membership_removal_anonymizes_and_rejoin_has_no_old_attribution(self):
        self.emit(actor=self.other)
        self.other_member.delete()
        event = Event.objects.get()
        self.assertIsNone(event.actor_user_id)
        self.assertIsNone(event.actor_membership_id)
        self.assertEqual(Daily.objects.get().actor_key, "unknown")
        new_member = Membership.objects.create(family=self.family, user=self.other)
        self.assertNotIn(str(new_member.pk), str(self.read("tasks/").data))

    def test_family_and_entity_deletion(self):
        task = Task.objects.create(family=self.family, title="Task", completed_at=timezone.now())
        self.assertTrue(Event.objects.filter(entity_id=task.pk).exists())
        task.delete()
        self.assertFalse(Event.objects.filter(entity_id=task.pk).exists())
        self.emit()
        self.family.delete()
        self.assertFalse(Event.objects.exists())
        self.assertFalse(Daily.objects.exists())

    def test_timezone_dst_boundaries_and_timezone_rebuild(self):
        spring = datetime(2026, 3, 28, 23, 30, tzinfo=dt_timezone.utc)
        summer = datetime(2026, 3, 29, 22, 30, tzinfo=dt_timezone.utc)
        self.emit(occurred_at=spring)
        self.emit(occurred_at=summer)
        self.assertEqual(list(Daily.objects.order_by("local_date").values_list("local_date", flat=True)), [spring.date() + timedelta(days=1), summer.date() + timedelta(days=1)])
        self.family.timezone = "UTC"
        self.family.save()
        self.assertEqual(list(Daily.objects.order_by("local_date").values_list("local_date", flat=True)), [spring.date(), summer.date()])
        self.assertEqual(self.read(**{"from": "2026-03-28", "to": "2026-03-29"}).data["summary"]["completed"], 2)

    def test_date_validation_and_pagination(self):
        for key, days in [("7d", 7), ("30d", 30), ("90d", 90), ("365d", 365)]:
            self.assertEqual(len(self.read(range=key).data["timeseries"]), days)
        self.assertEqual(self.read(range="999d").status_code, 400)
        self.assertEqual(self.read(**{"from": "2025-01-01", "to": "2026-10-14"}).status_code, 400)
        self.assertEqual(self.read("tasks/", page="bad").status_code, 400)
        for _ in range(51):
            self.emit()
        self.assertTrue(self.read("tasks/").data["has_next"])
        self.assertEqual(len(self.read("tasks/", page=2).data["results"]), 1)

    def test_backfill_idempotent_without_assignee_attribution(self):
        task = Task.objects.create(family=self.family, title="Historical", assignee=self.other, completed_at=timezone.now())
        routine = Routine.objects.create(family=self.family, name="History")
        RoutineLog.objects.create(routine=routine, done_at=timezone.now(), done_by=self.other, note="Hidden")
        call_command("rebuild_family_statistics", family=str(self.family.pk), backfill=True, stdout=StringIO())
        before = Event.objects.count()
        call_command("rebuild_family_statistics", family=str(self.family.pk), backfill=True, stdout=StringIO())
        self.assertEqual(Event.objects.count(), before)
        self.assertIsNone(Event.objects.get(entity_id=task.pk, action="completed").actor_user_id)

    def test_retention_and_constant_query_budget(self):
        self.assertIsNone(self.emit(occurred_at=timezone.now() - timedelta(days=731)))
        for _ in range(20):
            self.emit()
        with CaptureQueriesContext(connection) as queries:
            self.read()
        self.assertLessEqual(len(queries), 14, [q["sql"] for q in queries])
        self.assertFalse(any('FROM "family_statistics_familycontributionevent"' in q["sql"] for q in queries))


    def test_actor_finalization_cannot_relink_removed_member_after_rejoin(self):
        self.client.force_authenticate(self.other)
        task = Task.objects.create(family=self.family, title="Task")
        response = self.client.post("/api/actions/execute/", {"action_id": f"task:{task.pk}", "request_id": str(uuid4())}, format="json")
        self.assertEqual(response.status_code, 200)
        from family.unified_action_models import ActionCompletion
        completion = ActionCompletion.objects.get(pk=response.data["id"])
        self.other_member.delete()
        Membership.objects.create(family=self.family, user=self.other)
        completion.duration_minutes = 30
        completion.save()
        event = Event.objects.get(entity_id=task.id, action="completed")
        self.assertIsNone(event.actor_membership_id)
        self.assertIsNone(event.actor_user_id)

    def test_completion_key_normalizes_offsets(self):
        from .services import task_completion_key
        from zoneinfo import ZoneInfo
        when = timezone.now()
        self.assertEqual(task_completion_key("id", when), task_completion_key("id", when.astimezone(ZoneInfo("Europe/Berlin"))))

    def test_large_legacy_estimate_never_blocks_completion(self):
        task = Task.objects.create(family=self.family, title="Long project", estimate_minutes=20000)
        result = self.client.post("/api/actions/execute/", {"action_id": f"task:{task.pk}", "request_id": str(uuid4())}, format="json")
        self.assertEqual(result.status_code, 200)
        self.assertIsNone(Event.objects.get(entity_id=task.pk, action="completed").effort_minutes)
