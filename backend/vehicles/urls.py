from django.urls import path
from . import views

urlpatterns = [
    path("vehicles/", views.vehicles),
    path("vehicles/active/", views.active),
    path("vehicles/map-config/", views.map_config),
    path("vehicles/tiles/<int:z>/<int:x>/<int:y>/", views.tile),
    path("vehicles/<uuid:vehicle_id>/", views.vehicle_detail),
    path("vehicles/<uuid:vehicle_id>/fuel/", views.fuel),
    path("vehicles/<uuid:vehicle_id>/journeys/", views.journeys),
    path("vehicle-journeys/<uuid:journey_id>/", views.journey_detail),
    path("vehicle-journeys/<uuid:journey_id>/points/", views.points),
]
