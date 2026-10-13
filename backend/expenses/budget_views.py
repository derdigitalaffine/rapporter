from rest_framework import viewsets
from rest_framework.decorators import api_view
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response

from entitlements.services import require_capability
from .permissions import ExpenseAccess, finance_queryset
from family.models import Family
from .budget_serializers import ExpenseBudgetSerializer, BudgetAllocationReplaceSerializer
from .budget_services import ledger_budget_summary, replace_budget_allocations
from .models import Expense, ExpenseBudget, ExpenseLedger, get_default_expense_ledger


def _visible_expense(request, expense_id):
    queryset = Expense.objects.select_related("family", "ledger").filter(id=expense_id)
    if not request.user.is_superuser:
        queryset = queryset.filter(
            family__memberships__user=request.user,
            family__status=Family.Status.ACTIVE,
        )
    expense = queryset.distinct().first()
    if not expense:
        raise NotFound()
    require_capability(request.user, expense.family, "expenses")
    return expense


def _visible_ledger(request, ledger_id):
    queryset = ExpenseLedger.objects.select_related("family").filter(
        id=ledger_id,
        archived=False,
        family__status=Family.Status.ACTIVE,
    )
    if not request.user.is_superuser:
        queryset = queryset.filter(family__memberships__user=request.user)
    ledger = queryset.distinct().first()
    if not ledger:
        raise NotFound()
    require_capability(request.user, ledger.family, "expenses")
    return ledger


def _allocation_payload(expense, allocations):
    ledger = expense.ledger or get_default_expense_ledger(expense.family)
    return {
        "expense": str(expense.id),
        "ledger": str(ledger.id),
        "currency": ledger.base_currency.upper(),
        "allocations": [
            {
                "budget": str(allocation.budget_id),
                "budget_name": allocation.budget.name,
                "amount_in_budget_currency": str(allocation.amount_in_budget_currency),
            }
            for allocation in allocations
        ],
    }


class ExpenseBudgetViewSet(viewsets.ModelViewSet):
    permission_classes = [ExpenseAccess]
    serializer_class = ExpenseBudgetSerializer
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_queryset(self):
        user = self.request.user
        queryset = ExpenseBudget.objects.select_related("family", "ledger", "parent")
        if not user.is_superuser:
            queryset = queryset.filter(
                family__memberships__user=user,
                family__status=Family.Status.ACTIVE,
            )
        family_id = self.request.query_params.get("family")
        ledger_id = self.request.query_params.get("ledger")
        if family_id:
            queryset = queryset.filter(family_id=family_id)
        if ledger_id:
            queryset = queryset.filter(ledger_id=ledger_id)
        return finance_queryset(queryset, user).distinct()


@api_view(["GET", "PUT"])
def expense_budget_allocations(request, expense_id):
    expense = _visible_expense(request, expense_id)
    if request.method == "GET":
        allocations = expense.budget_allocations.select_related("budget", "budget__ledger").order_by("created_at")
        return Response(_allocation_payload(expense, allocations))

    serializer = BudgetAllocationReplaceSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    try:
        expense, allocations = replace_budget_allocations(
            expense,
            serializer.validated_data["allocations"],
        )
    except ValueError as exc:
        raise ValidationError({"allocations": [str(exc)]}) from exc
    return Response(_allocation_payload(expense, allocations))


@api_view(["GET"])
def expense_ledger_budget_summary(request, ledger_id):
    ledger = _visible_ledger(request, ledger_id)
    summary = ledger_budget_summary(ledger)
    budgets = ExpenseBudget.objects.filter(ledger=ledger, archived=False).select_related(
        "family", "ledger", "parent"
    )
    return Response(
        {
            "family": str(ledger.family_id),
            "ledger": str(ledger.id),
            "currency": summary["currency"],
            "budget_amount": None if summary["budget_amount"] is None else str(summary["budget_amount"]),
            "spent_amount": str(summary["spent_amount"]),
            "remaining_amount": None if summary["remaining_amount"] is None else str(summary["remaining_amount"]),
            "over_budget": summary["over_budget"],
            "unconverted_expense_count": summary["unconverted_expense_count"],
            "budgets": ExpenseBudgetSerializer(budgets, many=True, context={"request": request}).data,
        }
    )
