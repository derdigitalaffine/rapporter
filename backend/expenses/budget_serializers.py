from decimal import Decimal

from django.db import transaction
from django.db.models import Sum
from rest_framework import serializers

from .models import Expense, ExpenseBudget, ExpenseLedger
from .money import money
from .serializers import LocalizedDecimalField, _request_can_access_family
from .planning_serializers import BudgetPlanningConflict, RevisionCheckedPlanningSerializer


class ExpenseBudgetSerializer(RevisionCheckedPlanningSerializer):
    client_request_id = serializers.UUIDField(write_only=True, required=False, allow_null=True)
    amount = LocalizedDecimalField(max_digits=12, decimal_places=2)
    estimated_amount = LocalizedDecimalField(
        max_digits=12, decimal_places=2, allow_null=True, required=False, min_value=Decimal("0.00"),
    )
    currency = serializers.SerializerMethodField()
    spent_amount = serializers.SerializerMethodField()
    remaining_amount = serializers.SerializerMethodField()
    over_budget = serializers.SerializerMethodField()

    def get_currency(self, obj):
        return obj.ledger.base_currency.upper()

    def _spent(self, obj):
        cached = getattr(obj, "_budget_spent_amount", None)
        if cached is not None:
            return money(cached)
        value = obj.allocations.filter(
            expense__status=Expense.Status.POSTED,
        ).aggregate(total=Sum("amount_in_budget_currency"))["total"] or Decimal("0.00")
        obj._budget_spent_amount = value
        return money(value)

    def get_spent_amount(self, obj):
        return self._spent(obj)

    def get_remaining_amount(self, obj):
        return money(obj.amount - self._spent(obj))

    def get_over_budget(self, obj):
        return self._spent(obj) > money(obj.amount)

    def validate_amount(self, value):
        if value < 0:
            raise serializers.ValidationError("Budget darf nicht negativ sein.")
        return value

    @transaction.atomic
    def create(self, validated_data):
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
                return existing
        return super().create(validated_data)

    def update(self, instance, validated_data):
        validated_data.pop("client_request_id", None)
        return super().update(instance, validated_data)

    def validate(self, attrs):
        request = self.context.get("request")
        family = attrs.get("family") or getattr(self.instance, "family", None)
        ledger = attrs.get("ledger") or getattr(self.instance, "ledger", None)
        parent = attrs.get("parent", getattr(self.instance, "parent", None))

        if not family or not _request_can_access_family(request, family):
            raise serializers.ValidationError({"family": "Familie ist für diesen Benutzer nicht verfügbar."})
        if not ledger or ledger.family_id != family.id or ledger.archived:
            raise serializers.ValidationError({"ledger": "Abrechnungskreis ist für diese Familie nicht verfügbar."})

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
        if starts_on and ends_on and ends_on < starts_on:
            raise serializers.ValidationError({"ends_on": "Enddatum darf nicht vor dem Startdatum liegen."})
        if period_type == ExpenseBudget.PeriodType.DATE_RANGE and (not starts_on or not ends_on):
            raise serializers.ValidationError({"period_type": "Für einen Datumszeitraum sind Start- und Enddatum erforderlich."})
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
            "currency",
            "period_type",
            "starts_on",
            "ends_on",
            "archived",
            "spent_amount",
            "remaining_amount",
            "over_budget",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "currency",
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
