from django.db import transaction
from rest_framework import serializers
from rest_framework.exceptions import APIException


class BudgetPlanningConflict(APIException):
    status_code = 409
    default_detail = "Die Budgetplanung wurde inzwischen geändert. Bitte den aktuellen Stand laden."
    default_code = "budget_planning_conflict"


class RevisionCheckedPlanningSerializer(serializers.ModelSerializer):
    expected_updated_at = serializers.DateTimeField(write_only=True, required=False)

    def create(self, validated_data):
        validated_data.pop("expected_updated_at", None)
        return super().create(validated_data)

    @transaction.atomic
    def update(self, instance, validated_data):
        expected = validated_data.pop("expected_updated_at", None)
        # Lock the canonical row only, never its nullable/context joins.
        current = type(instance).objects.select_for_update().get(pk=instance.pk)
        if expected is not None and expected != current.updated_at:
            raise BudgetPlanningConflict()
        return super().update(current, validated_data)
