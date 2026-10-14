from decimal import Decimal

from django.db import transaction
from rest_framework import serializers

from family.models import Membership
from .models import ExpenseBudget, ExpenseLedger
from .money import money
from .participant_services import (
    can_manage_participant_plans,
    current_plan_signature,
    replace_participant_plans,
    requested_plan_signature,
)
from .period_models import ExpenseBudgetPeriod
from .period_services import (
    RECURRING_PERIOD_TYPES,
    close_current_period,
    configure_current_period,
    ensure_budget_period,
    period_state,
    validate_period_type_change,
)
from .serializers import LocalizedDecimalField, _request_can_access_family
from .planning_serializers import BudgetPlanningConflict, RevisionCheckedPlanningSerializer


class ParticipantPlanWriteSerializer(serializers.Serializer):
    member = serializers.UUIDField()
    spending_limit = LocalizedDecimalField(
        max_digits=12,
        decimal_places=2,
        allow_null=True,
        required=False,
        min_value=Decimal("0.00"),
    )
    planned_share = LocalizedDecimalField(
        max_digits=12,
        decimal_places=2,
        allow_null=True,
        required=False,
        min_value=Decimal("0.00"),
    )

    def validate(self, attrs):
        if attrs.get("spending_limit") is None and attrs.get("planned_share") is None:
            raise serializers.ValidationError("Mindestens Limit oder geplanter Kostenanteil ist erforderlich.")
        return attrs


class ExpenseBudgetSerializer(RevisionCheckedPlanningSerializer):
    client_request_id = serializers.UUIDField(write_only=True, required=False, allow_null=True)
    participant_plans = ParticipantPlanWriteSerializer(many=True, write_only=True, required=False)
    amount = LocalizedDecimalField(max_digits=12, decimal_places=2)
    estimated_amount = LocalizedDecimalField(
        max_digits=12, decimal_places=2, allow_null=True, required=False, min_value=Decimal("0.00"),
    )
    currency = serializers.SerializerMethodField()
    spent_amount = serializers.SerializerMethodField()
    remaining_amount = serializers.SerializerMethodField()
    over_budget = serializers.SerializerMethodField()
    carryover_amount = serializers.SerializerMethodField()
    period_starts_on = serializers.SerializerMethodField()
    period_ends_on = serializers.SerializerMethodField()
    rollover_policy = serializers.SerializerMethodField()

    def to_internal_value(self, data):
        policy = data.get("rollover_policy", serializers.empty)
        clean = data.copy()
        if "rollover_policy" in clean:
            clean.pop("rollover_policy")
        attrs = super().to_internal_value(clean)
        if policy is not serializers.empty:
            allowed = {choice for choice, _ in ExpenseBudgetPeriod.RolloverPolicy.choices}
            if policy not in allowed:
                raise serializers.ValidationError({
                    "rollover_policy": "Übertrag muss 'reset' oder 'carry_positive' sein."
                })
            attrs["_rollover_policy"] = policy
        return attrs

    def get_currency(self, obj):
        return obj.ledger.base_currency.upper()

    def _state(self, obj):
        cached = getattr(obj, "_active_period_state", None)
        if cached is None:
            cached = period_state(obj)
            obj._active_period_state = cached
        return cached

    def _spent(self, obj):
        return self._state(obj)["spent_amount"]

    def get_spent_amount(self, obj):
        return self._spent(obj)

    def get_carryover_amount(self, obj):
        return self._state(obj)["carryover_amount"]

    def get_period_starts_on(self, obj):
        return self._state(obj)["starts_on"]

    def get_period_ends_on(self, obj):
        return self._state(obj)["ends_on"]

    def get_rollover_policy(self, obj):
        return self._state(obj)["rollover_policy"]

    def get_remaining_amount(self, obj):
        state = self._state(obj)
        return money(state["planned_amount"] - state["spent_amount"])

    def get_over_budget(self, obj):
        state = self._state(obj)
        # Compatibility: this keeps the established "actual spend exceeded the
        # planned amount" signal. Carryover/reservations belong to availability
        # and its separate over_available state.
        return state["spent_amount"] > state["planned_amount"]

    def validate_amount(self, value):
        if value < 0:
            raise serializers.ValidationError("Budget darf nicht negativ sein.")
        return value

    def _replace_plans(self, budget, participant_plans):
        if participant_plans is serializers.empty:
            return
        try:
            replace_participant_plans(
                budget=budget,
                rows=participant_plans,
                user=self.context["request"].user,
            )
        except PermissionError as exc:
            raise serializers.ValidationError({"participant_plans": str(exc)}) from exc
        except ValueError as exc:
            raise serializers.ValidationError({"participant_plans": str(exc)}) from exc

    @transaction.atomic
    def create(self, validated_data):
        participant_plans = validated_data.pop("participant_plans", serializers.empty)
        rollover_policy = validated_data.pop("_rollover_policy", None)
        ledger = ExpenseLedger.objects.select_for_update().get(pk=validated_data["ledger"].pk)
        if ledger.archived:
            raise serializers.ValidationError({"ledger": "Abrechnungskreis ist nicht verfügbar."})
        request_id = validated_data.get("client_request_id")
        if request_id:
            existing = ExpenseBudget.objects.filter(ledger=ledger, client_request_id=request_id).first()
            if existing:
                for field in ("name", "amount", "estimated_amount", "parent", "period_type", "starts_on", "ends_on", "archived"):
                    if field in validated_data and getattr(existing, field) != validated_data[field]:
                        raise BudgetPlanningConflict()
                if rollover_policy is not None:
                    state = period_state(existing)
                    if existing.period_type not in RECURRING_PERIOD_TYPES or state["rollover_policy"] != rollover_policy:
                        raise BudgetPlanningConflict()
                if participant_plans is not serializers.empty and requested_plan_signature(participant_plans) != current_plan_signature(existing):
                    raise BudgetPlanningConflict()
                return existing
        created = super().create(validated_data)
        configure_current_period(created, rollover_policy=rollover_policy)
        self._replace_plans(created, participant_plans)
        return created

    @transaction.atomic
    def update(self, instance, validated_data):
        participant_plans = validated_data.pop("participant_plans", serializers.empty)
        rollover_policy = validated_data.pop("_rollover_policy", None)
        validated_data.pop("client_request_id", None)
        next_period_type = validated_data.get("period_type", instance.period_type)
        try:
            validate_period_type_change(instance, next_period_type)
        except ValueError as exc:
            raise serializers.ValidationError({"period_type": str(exc)}) from exc

        will_archive = validated_data.get("archived", instance.archived)
        # Roll expired periods while the old plan value is still present. This
        # prevents a plan edit from retroactively rewriting skipped history.
        if (
            instance.period_type in RECURRING_PERIOD_TYPES
            and next_period_type == instance.period_type
            and not instance.archived
            and not will_archive
        ):
            ensure_budget_period(instance)

        updated = super().update(instance, validated_data)
        if updated.archived:
            close_current_period(updated)
        else:
            configure_current_period(updated, rollover_policy=rollover_policy)
        self._replace_plans(updated, participant_plans)
        return updated

    def validate(self, attrs):
        request = self.context.get("request")
        family = attrs.get("family") or getattr(self.instance, "family", None)
        ledger = attrs.get("ledger") or getattr(self.instance, "ledger", None)
        parent = attrs.get("parent", getattr(self.instance, "parent", None))
        participant_plans = attrs.get("participant_plans", serializers.empty)

        if not family or not _request_can_access_family(request, family):
            raise serializers.ValidationError({"family": "Familie ist für diesen Benutzer nicht verfügbar."})
        if not ledger or ledger.family_id != family.id or ledger.archived:
            raise serializers.ValidationError({"ledger": "Abrechnungskreis ist für diese Familie nicht verfügbar."})

        if participant_plans is not serializers.empty:
            if not can_manage_participant_plans(request.user, family):
                raise serializers.ValidationError({
                    "participant_plans": "Teilnehmerplanung darf nur von Erwachsenen verwaltet werden."
                })
            member_ids = [str(row["member"]) for row in participant_plans]
            if len(member_ids) != len(set(member_ids)):
                raise serializers.ValidationError({"participant_plans": "Jede Person darf nur einmal vorkommen."})
            found = set(
                str(value)
                for value in Membership.objects.filter(family=family, id__in=member_ids).values_list("id", flat=True)
            )
            if set(member_ids) != found:
                raise serializers.ValidationError({
                    "participant_plans": "Mindestens eine Person gehört nicht zu dieser Familie."
                })

        if self.instance:
            if "family" in attrs and family.id != self.instance.family_id:
                raise serializers.ValidationError({"family": "Die Familie eines Budgets kann nicht geändert werden."})
            if "ledger" in attrs and ledger.id != self.instance.ledger_id:
                raise serializers.ValidationError({"ledger": "Der Abrechnungskreis eines Budgets kann nicht geändert werden."})

        if parent:
            if parent.family_id != family.id or parent.ledger_id != ledger.id or parent.archived:
                raise serializers.ValidationError({"parent": "Übergeordnetes Budget ist nicht verfügbar."})
            current = parent
            while current is not None:
                if self.instance and current.id == self.instance.id:
                    raise serializers.ValidationError({"parent": "Budgets dürfen keinen Zyklus bilden."})
                current = current.parent

        starts_on = attrs.get("starts_on", getattr(self.instance, "starts_on", None))
        ends_on = attrs.get("ends_on", getattr(self.instance, "ends_on", None))
        period_type = attrs.get("period_type", getattr(self.instance, "period_type", ExpenseBudget.PeriodType.OPEN))
        rollover_policy = attrs.get("_rollover_policy")
        if starts_on and ends_on and ends_on < starts_on:
            raise serializers.ValidationError({"ends_on": "Enddatum darf nicht vor dem Startdatum liegen."})
        if period_type == ExpenseBudget.PeriodType.DATE_RANGE and (not starts_on or not ends_on):
            raise serializers.ValidationError({"period_type": "Für einen Datumszeitraum sind Start- und Enddatum erforderlich."})
        if rollover_policy is not None and period_type not in RECURRING_PERIOD_TYPES:
            raise serializers.ValidationError({
                "rollover_policy": "Restmittelübertrag ist nur für Monats- oder Jahresbudgets verfügbar."
            })
        return attrs

    class Meta:
        model = ExpenseBudget
        # Retry keys are optional and resolved under the ledger lock in create().
        validators = []
        fields = [
            "id",
            "family",
            "ledger",
            "parent",
            "name",
            "amount",
            "estimated_amount",
            "expected_updated_at",
            "client_request_id",
            "participant_plans",
            "currency",
            "period_type",
            "starts_on",
            "ends_on",
            "rollover_policy",
            "period_starts_on",
            "period_ends_on",
            "carryover_amount",
            "archived",
            "spent_amount",
            "remaining_amount",
            "over_budget",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "currency",
            "rollover_policy",
            "period_starts_on",
            "period_ends_on",
            "carryover_amount",
            "spent_amount",
            "remaining_amount",
            "over_budget",
            "created_at",
            "updated_at",
        ]


class BudgetAllocationLineSerializer(serializers.Serializer):
    budget = serializers.UUIDField()
    amount_in_budget_currency = LocalizedDecimalField(max_digits=12, decimal_places=2)

    def validate_amount_in_budget_currency(self, value):
        if value <= 0:
            raise serializers.ValidationError("Budgetanteil muss größer als 0 sein.")
        return value


class BudgetAllocationReplaceSerializer(serializers.Serializer):
    allocations = BudgetAllocationLineSerializer(many=True)
