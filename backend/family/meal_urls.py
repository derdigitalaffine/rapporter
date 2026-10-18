from django.urls import path
from rest_framework.routers import DefaultRouter

from .meal_views import (
    MealDishViewSet,
    MealPlanDayTagViewSet,
    MealPlanEntryViewSet,
    MealPlanTemplateViewSet,
    MealPlanTodayView,
    MealShoppingCommitView,
    MealShoppingDiffView,
    MealShoppingPreviewView,
    MealTagViewSet,
    MealTemplateApplyView,
    MealTemplateFromWeekView,
)

router = DefaultRouter()
router.register("meal-tags", MealTagViewSet, basename="meal-tag")
router.register("meal-dishes", MealDishViewSet, basename="meal-dish")
router.register("meal-plan-entries", MealPlanEntryViewSet, basename="meal-plan-entry")
router.register("meal-plan-day-tags", MealPlanDayTagViewSet, basename="meal-plan-day-tag")
router.register("meal-plan-templates", MealPlanTemplateViewSet, basename="meal-plan-template")

urlpatterns = [
    path("meal-plan/today/", MealPlanTodayView.as_view(), name="meal-plan-today"),
    path("meal-plan/templates/from-week/", MealTemplateFromWeekView.as_view(), name="meal-plan-template-from-week"),
    path("meal-plan/templates/<uuid:pk>/apply/", MealTemplateApplyView.as_view(), name="meal-plan-template-apply"),
    path("meal-plan/shopping-preview/", MealShoppingPreviewView.as_view(), name="meal-plan-shopping-preview"),
    path("meal-plan/shopping-diff/", MealShoppingDiffView.as_view(), name="meal-plan-shopping-diff"),
    path("meal-plan/shopping-commit/", MealShoppingCommitView.as_view(), name="meal-plan-shopping-commit"),
] + router.urls
