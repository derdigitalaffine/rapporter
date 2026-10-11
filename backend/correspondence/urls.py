from django.urls import path

from .views import correspondence_action, correspondence_review

urlpatterns = [
    path("correspondence/<uuid:document_id>/review/", correspondence_review, name="correspondence-review"),
    path("correspondence/<uuid:document_id>/actions/", correspondence_action, name="correspondence-action"),
]
