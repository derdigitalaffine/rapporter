from django.urls import include, path
from rest_framework.routers import DefaultRouter
from .views import FamilyViewSet, TaskListViewSet, TaskViewSet, ShoppingListViewSet, ShoppingItemViewSet, RoutineViewSet, IntegrationSourceViewSet, AutomationRuleViewSet, FamilyEventViewSet, InboxItemViewSet, dashboard, health
from .invitation_views import FamilyInvitationViewSet, invitation_info, invitation_register, invitation_accept
from .membership_views import MembershipViewSet
from .smart_views import (
    integration_oauth_callback,
    integration_oauth_start,
    shopping_clear_checked,
    shopping_quick_add,
    shopping_toggle_favorite,
    smart_integration_catalog,
    smart_integration_connect,
    smart_integration_sync,
    smart_integration_sync_all,
    task_quick_add,
)

router = DefaultRouter()
router.register("families", FamilyViewSet, basename="family")
router.register("memberships", MembershipViewSet, basename="membership")
router.register("task-lists", TaskListViewSet, basename="task-list")
router.register("tasks", TaskViewSet, basename="task")
router.register("shopping-lists", ShoppingListViewSet, basename="shopping-list")
router.register("shopping-items", ShoppingItemViewSet, basename="shopping-item")
router.register("routines", RoutineViewSet, basename="routine")
router.register("integrations", IntegrationSourceViewSet, basename="integration")
router.register("automation-rules", AutomationRuleViewSet, basename="automation-rule")
router.register("events", FamilyEventViewSet, basename="event")
router.register("inbox", InboxItemViewSet, basename="inbox")
router.register("invitations", FamilyInvitationViewSet, basename="invitation")

urlpatterns = [
    path("health/", health),
    path("dashboard/", dashboard),
    path("invite/<str:token>/", invitation_info),
    path("invite/<str:token>/register/", invitation_register),
    path("invite/<str:token>/accept/", invitation_accept),
    path("smart/tasks/quick-add/", task_quick_add),
    path("smart/shopping/quick-add/", shopping_quick_add),
    path("smart/shopping/<uuid:item_id>/favorite/", shopping_toggle_favorite),
    path("smart/shopping-lists/<uuid:list_id>/clear-checked/", shopping_clear_checked),
    path("integration-hub/catalog/", smart_integration_catalog),
    path("integration-hub/connect/", smart_integration_connect),
    path("integration-hub/sync-all/", smart_integration_sync_all),
    path("integration-hub/<uuid:source_id>/sync/", smart_integration_sync),
    path("integration-oauth/start/", integration_oauth_start),
    path("integration-oauth/callback/", integration_oauth_callback),
    path("", include(router.urls)),
]
