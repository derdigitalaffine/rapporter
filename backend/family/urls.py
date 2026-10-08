from django.urls import include, path
from rest_framework.routers import DefaultRouter
from .views import FamilyViewSet, TaskViewSet, ShoppingListViewSet, ShoppingItemViewSet, RoutineViewSet, IntegrationSourceViewSet, FamilyEventViewSet, InboxItemViewSet, dashboard, health

router = DefaultRouter()
router.register("families", FamilyViewSet, basename="family")
router.register("tasks", TaskViewSet, basename="task")
router.register("shopping-lists", ShoppingListViewSet, basename="shopping-list")
router.register("shopping-items", ShoppingItemViewSet, basename="shopping-item")
router.register("routines", RoutineViewSet, basename="routine")
router.register("integrations", IntegrationSourceViewSet, basename="integration")
router.register("events", FamilyEventViewSet, basename="event")
router.register("inbox", InboxItemViewSet, basename="inbox")

urlpatterns = [path("health/", health), path("dashboard/", dashboard), path("", include(router.urls))]
