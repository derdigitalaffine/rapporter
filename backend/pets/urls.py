from django.urls import path

from . import views

urlpatterns = [
    path("pets/module/", views.module_detail),
    path("pets/care-circle/", views.care_circle),
    path("pets/profiles/", views.pet_profiles),
    path("pets/profiles/<uuid:pet_id>/", views.pet_detail),
    path("pets/<uuid:pet_id>/care/", views.pet_care),
    path("pets/care/<uuid:log_id>/", views.pet_care_detail),
    path("pets/<uuid:pet_id>/health-events/", views.pet_health_events),
    path("pets/health-events/<uuid:event_id>/", views.pet_health_event_detail),
    path("pets/<uuid:pet_id>/medications/", views.pet_medications),
    path("pets/medications/<uuid:medication_id>/", views.pet_medication_detail),
    path("pets/medications/<uuid:medication_id>/dose/", views.pet_medication_dose),
    path("pets/<uuid:pet_id>/weights/", views.pet_weights),
    path("pets/<uuid:pet_id>/observations/", views.pet_observations),
    path("pets/<uuid:pet_id>/documents/", views.pet_documents),
    path("pets/documents/<uuid:document_id>/", views.pet_document_detail),
    path("pets/documents/<uuid:document_id>/apply/", views.pet_document_apply),
    path("pets/<uuid:pet_id>/vet-event/", views.pet_vet_event),
    path("pets/<uuid:pet_id>/vet-questions/", views.pet_vet_questions),
    path("pets/vet-questions/<uuid:question_id>/", views.pet_vet_question_detail),
    path("pets/<uuid:pet_id>/handover/", views.pet_handover),
    path("pets/<uuid:pet_id>/emergency-card/", views.pet_emergency_card),
    path("pets/<uuid:pet_id>/report/", views.pet_report),
    path("pets/<uuid:pet_id>/shares/", views.pet_shares),
    path("pets/shares/<uuid:share_id>/revoke/", views.pet_share_revoke),
    path("pets/share/<str:token>/", views.public_pet_share),
]
