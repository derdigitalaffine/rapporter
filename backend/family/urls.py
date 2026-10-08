from django.urls import include, path
from rest_framework.routers import DefaultRouter
from .views import FamilyViewSet, TaskListViewSet, TaskViewSet, ShoppingListViewSet, ShoppingItemViewSet, RoutineViewSet, IntegrationSourceViewSet, AutomationRuleViewSet, FamilyEventViewSet, InboxItemViewSet, dashboard, health
from .invitation_views import FamilyInvitationViewSet, invitation_info, invitation_register, invitation_accept

router = DefaultRouter()
router.register("families", FamilyViewSet, basename="family")
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
    path("", include(router.urls)),
]
