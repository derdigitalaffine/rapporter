from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .budget_views import ExpenseBudgetViewSet, expense_budget_allocations, expense_ledger_budget_summary
from .views import ExpenseLedgerViewSet, ExpenseViewSet, SettlementViewSet
from .receipt_views import receipt_file
from .trip_views import trip_expense_ledger

router = DefaultRouter()
router.register("expense-ledgers", ExpenseLedgerViewSet, basename="expense-ledger")
router.register("expense-budgets", ExpenseBudgetViewSet, basename="expense-budget")
router.register("expenses", ExpenseViewSet, basename="expense")
router.register("expense-settlements", SettlementViewSet, basename="expense-settlement")

settlement_collection = SettlementViewSet.as_view({"get": "list", "post": "create"})
settlement_void = SettlementViewSet.as_view({"post": "void"})

urlpatterns = [
    path("expense-ledgers/for-trip/", trip_expense_ledger, name="expense-ledger-for-trip"),
    path("expense-ledgers/<uuid:ledger_id>/budget-summary/", expense_ledger_budget_summary, name="expense-ledger-budget-summary"),
    path("expenses/<uuid:expense_id>/budget-allocations/", expense_budget_allocations, name="expense-budget-allocations"),
    path("expenses/settlements/", settlement_collection, name="expense-settlement-collection"),
    path("expenses/settlements/<uuid:pk>/void/", settlement_void, name="expense-settlement-void"),
    path("expenses/<uuid:expense_id>/receipt-file/", receipt_file, name="expense-receipt-file"),
    path("", include(router.urls)),
]
