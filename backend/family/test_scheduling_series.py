from datetime import date

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase

from .models import Family, FamilyEvent, Membership
from .scheduling_models import (
    SchedulingDependency,
    SchedulingOccurrenceOverride,
    SchedulingRuleVersion,
    SchedulingSeries,
    SchedulingTemplate,
)
from .scheduling_series import (
    append_rule_version,
    create_dependency,
    create_series,
    create_template,
    record_occurrence_override,
    rule_version_for_occurrence,
)
from .unified_action_models import Action


User = get_user_model()


def recurring_rule(anchor="2026-01-05", weekday="MO"):
    return {
        "version": "scheduling-rule-v1",
        "timezone": "Europe/Berlin",
        "time_mode": "wall_clock",
        "anchor_date": anchor,
        "recurrence": {"frequency": "weekly", "interval": 1, "weekdays": [weekday]},
    }


class SchedulingSeriesTests(TestCase):
    def setUp(self):
        self.family = Family.objects.create(name="Test family", slug="schedule-test", timezone="Europe/Berlin")
        self.owner = User.objects.create_user(username="schedule-owner", password="x")
        self.adult = User.objects.create_user(username="schedule-adult", password="x")
        self.teen = User.objects.create_user(username="schedule-teen", password="x")
        self.other_teen = User.objects.create_user(username="schedule-other-teen", password="x")
        self.child = User.objects.create_user(username="schedule-child", password="x")
        self.guest = User.objects.create_user(username="schedule-guest", password="x")
        for user, role in [
            (self.owner, Membership.Role.OWNER),
            (self.adult, Membership.Role.ADULT),
            (self.teen, Membership.Role.TEEN),
            (self.other_teen, Membership.Role.TEEN),
            (self.child, Membership.Role.CHILD),
            (self.guest, Membership.Role.GUEST),
        ]:
            Membership.objects.create(family=self.family, user=user, role=role)
        self.event = FamilyEvent.objects.create(
            family=self.family,
            type="calendar.event",
            title="Quarterly planning",
        )
        self.action = Action.objects.create(
            family=self.family,
            title="Put bins out",
            kind_hint="todo",
            created_by=self.owner,
        )

    def test_series_wraps_canonical_event_and_keeps_first_rule_version(self):
        series = create_series(
            target_type=SchedulingSeries.TargetType.EVENT,
            target_id=self.event.id,
            rule=recurring_rule(),
            actor=self.teen,
        )
        self.assertEqual(series.family, self.family)
        self.assertEqual(series.target_id, self.event.id)
        self.assertEqual(series.current_version, 1)
        version = series.rule_versions.get()
        self.assertEqual(version.version, 1)
        self.assertEqual(version.change_scope, SchedulingRuleVersion.ChangeScope.INITIAL)
        self.assertEqual(version.rule["version"], "scheduling-rule-v1")
        self.assertEqual(version.rule["timezone"], "Europe/Berlin")

    def test_one_domain_object_has_only_one_scheduling_series(self):
        create_series(
            target_type=SchedulingSeries.TargetType.ACTION,
            target_id=self.action.id,
            rule=recurring_rule(),
            actor=self.owner,
        )
        with self.assertRaisesRegex(ValidationError, "already exists"):
            create_series(
                target_type=SchedulingSeries.TargetType.ACTION,
                target_id=self.action.id,
                rule=recurring_rule(weekday="TH"),
                actor=self.owner,
            )

    def test_creator_or_adult_can_version_series_but_unrelated_teen_cannot(self):
        series = create_series(
            target_type=SchedulingSeries.TargetType.EVENT,
            target_id=self.event.id,
            rule=recurring_rule(),
            actor=self.teen,
        )
        append_rule_version(
            series=series,
            rule=recurring_rule(weekday="TU"),
            actor=self.teen,
            scope=SchedulingRuleVersion.ChangeScope.FUTURE,
            effective_from="2026-03-01",
        )
        with self.assertRaises(PermissionDenied):
            append_rule_version(
                series=series,
                rule=recurring_rule(weekday="WE"),
                actor=self.other_teen,
                scope=SchedulingRuleVersion.ChangeScope.WHOLE,
            )
        third = append_rule_version(
            series=series,
            rule=recurring_rule(weekday="TH"),
            actor=self.adult,
            scope=SchedulingRuleVersion.ChangeScope.WHOLE,
        )
        self.assertEqual(third.version, 3)
        series.refresh_from_db()
        self.assertEqual(series.current_version, 3)

    def test_future_split_is_selected_by_occurrence_and_whole_edit_resets_baseline(self):
        series = create_series(
            target_type=SchedulingSeries.TargetType.EVENT,
            target_id=self.event.id,
            rule=recurring_rule(weekday="MO"),
            actor=self.owner,
        )
        future = append_rule_version(
            series=series,
            rule=recurring_rule(weekday="TU"),
            actor=self.owner,
            scope=SchedulingRuleVersion.ChangeScope.FUTURE,
            effective_from=date(2026, 3, 1),
        )
        self.assertEqual(rule_version_for_occurrence(series, "2026-02-01").version, 1)
        self.assertEqual(rule_version_for_occurrence(series, "2026-04-01").version, future.version)

        whole = append_rule_version(
            series=series,
            rule=recurring_rule(weekday="WE"),
            actor=self.owner,
            scope=SchedulingRuleVersion.ChangeScope.WHOLE,
        )
        self.assertEqual(rule_version_for_occurrence(series, "2026-04-01").version, whole.version)

    def test_future_edit_requires_effective_date_and_whole_edit_rejects_it(self):
        series = create_series(
            target_type=SchedulingSeries.TargetType.EVENT,
            target_id=self.event.id,
            rule=recurring_rule(),
            actor=self.owner,
        )
        with self.assertRaises(ValidationError):
            append_rule_version(
                series=series,
                rule=recurring_rule(),
                actor=self.owner,
                scope=SchedulingRuleVersion.ChangeScope.FUTURE,
            )
        with self.assertRaises(ValidationError):
            append_rule_version(
                series=series,
                rule=recurring_rule(),
                actor=self.owner,
                scope=SchedulingRuleVersion.ChangeScope.WHOLE,
                effective_from="2026-03-01",
            )

    def test_individual_occurrence_override_is_available_to_normal_member_not_guest(self):
        series = create_series(
            target_type=SchedulingSeries.TargetType.EVENT,
            target_id=self.event.id,
            rule=recurring_rule(),
            actor=self.owner,
        )
        override = record_occurrence_override(
            series=series,
            occurrence_key="2026-03-02",
            kind=SchedulingOccurrenceOverride.Kind.OVERRIDE,
            actor=self.child,
            payload={"starts_at": "2026-03-03T09:00:00+01:00"},
            detached_fields=["starts_at", "starts_at"],
        )
        self.assertEqual(override.detached_fields, ["starts_at"])
        self.assertEqual(override.rule_version, 1)
        with self.assertRaises(PermissionDenied):
            record_occurrence_override(
                series=series,
                occurrence_key="2026-03-09",
                kind=SchedulingOccurrenceOverride.Kind.SKIP,
                actor=self.guest,
            )

    def test_shared_templates_are_manager_only_but_personal_templates_are_not(self):
        personal = create_template(
            family=self.family,
            name="School week",
            rule=recurring_rule(),
            actor=self.teen,
        )
        self.assertEqual(personal.scope, SchedulingTemplate.Scope.PERSONAL)
        self.assertEqual(personal.owner, self.teen)
        with self.assertRaises(PermissionDenied):
            create_template(
                family=self.family,
                name="Family planning",
                rule=recurring_rule(),
                actor=self.teen,
                scope=SchedulingTemplate.Scope.FAMILY,
            )
        shared = create_template(
            family=self.family,
            name="Family planning",
            rule=recurring_rule(),
            actor=self.adult,
            scope=SchedulingTemplate.Scope.FAMILY,
        )
        self.assertIsNone(shared.owner)

    def test_dependency_can_anchor_event_or_action_and_occurrence_scope_requires_key(self):
        dep = create_dependency(
            family=self.family,
            anchor_type=SchedulingSeries.TargetType.EVENT,
            anchor_id=self.event.id,
            output_type=SchedulingDependency.OutputType.ACTION,
            relative_rule={"version": "relative-schedule-v1", "direction": "before", "days": 3},
            actor=self.teen,
            anchor_scope=SchedulingDependency.AnchorScope.OCCURRENCE,
            anchor_occurrence_key="2026-11-12",
            output_blueprint={"title": "Prepare bins"},
            inheritance={"family": "anchor"},
        )
        self.assertEqual(dep.anchor_occurrence_key, "2026-11-12")
        self.assertEqual(dep.output_type, SchedulingDependency.OutputType.ACTION)
        with self.assertRaises(ValidationError):
            create_dependency(
                family=self.family,
                anchor_type=SchedulingSeries.TargetType.ACTION,
                anchor_id=self.action.id,
                output_type=SchedulingDependency.OutputType.EVENT,
                relative_rule={"direction": "after", "days": 1},
                actor=self.owner,
                anchor_scope=SchedulingDependency.AnchorScope.OCCURRENCE,
            )
