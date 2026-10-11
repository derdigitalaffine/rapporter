from django.urls import path

from .views import notification_collection, notification_detail, notification_read_all

urlpatterns = [
    path("notifications/", notification_collection, name="notification_collection"),
    path("notifications/read-all/", notification_read_all, name="notification_read_all"),
    path("notifications/<uuid:notification_id>/", notification_detail, name="notification_detail"),
]
