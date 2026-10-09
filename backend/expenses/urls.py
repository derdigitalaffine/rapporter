from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import ExpenseViewSet, SettlementViewSet
from .receipt_views import receipt_file

router = DefaultRouter()
router.register("expenses", ExpenseViewSet, basename="expense")
router.register("expense-settlements", SettlementViewSet, basename="expense-settlement")

urlpatterns = [
    path("expenses/<uuid:expense_id>/receipt-file/", receipt_file, name="expense-receipt-file"),
    path("", include(router.urls)),
]
