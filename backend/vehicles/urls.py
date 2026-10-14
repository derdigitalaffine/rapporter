from django.urls import path
from . import views

urlpatterns = [
    path("vehicles/", views.vehicles),
    path("vehicles/active/", views.active),
    path("vehicles/map-config/", views.map_config),
    path("vehicles/<uuid:vehicle_id>/", views.vehicle_detail),
    path("vehicles/<uuid:vehicle_id>/fuel/", views.fuel),
    path("vehicles/<uuid:vehicle_id>/journeys/", views.journeys),
    path("vehicles/<uuid:vehicle_id>/journeys/manual/", views.manual_journey),
    path("vehicles/<uuid:vehicle_id>/journey-suggestions/", views.journey_suggestions),
    path("vehicles/<uuid:vehicle_id>/journey-report/", views.journey_report),
    path("vehicle-journeys/<uuid:journey_id>/", views.journey_detail),
    path("vehicle-journeys/<uuid:journey_id>/points/", views.points),
    path("vehicle-journeys/<uuid:journey_id>/classify/", views.classify_journey),
    path("vehicle-journeys/<uuid:journey_id>/correct/", views.correct_journey),
    path("vehicle-journeys/<uuid:journey_id>/void/", views.void_journey),
    path("vehicle-journeys/<uuid:journey_id>/revisions/", views.journey_revisions),
]
