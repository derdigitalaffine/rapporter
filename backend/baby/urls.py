from django.urls import path

from . import extra_views, media_views, secure_views, views


urlpatterns = [
    path("baby/module/", views.module_detail),
    path("baby/care-circle/", views.care_circle),
    path("baby/pregnancies/", views.pregnancies),
    path("baby/pregnancies/<uuid:pregnancy_id>/", secure_views.pregnancy_detail),
    path("baby/pregnancies/<uuid:pregnancy_id>/birth/", secure_views.pregnancy_birth),
    path("baby/pregnancies/<uuid:pregnancy_id>/birth-preferences/", extra_views.birth_preferences),
    path("baby/pregnancies/<uuid:pregnancy_id>/prenatal-event/", extra_views.prenatal_event),
    path("baby/pregnancies/<uuid:pregnancy_id>/templates/", views.pregnancy_templates),
    path("baby/pregnancies/<uuid:pregnancy_id>/utilities/", views.pregnancy_utilities),
    path("baby/pregnancy-utilities/<uuid:session_id>/", views.pregnancy_utility_detail),
    path("baby/pregnancies/<uuid:pregnancy_id>/journal/", views.pregnancy_journal),
    path("baby/profiles/", secure_views.baby_profiles),
    path("baby/profiles/<uuid:baby_id>/care/", views.baby_care),
    path("baby/care/<uuid:care_id>/", views.baby_care_detail),
    path("baby/profiles/<uuid:baby_id>/viewed/", views.baby_mark_viewed),
    path("baby/profiles/<uuid:baby_id>/growth/", views.baby_growth),
    path("baby/profiles/<uuid:baby_id>/growth-reference/", views.baby_growth_reference),
    path("baby/profiles/<uuid:baby_id>/development/", views.baby_development),
    path("baby/profiles/<uuid:baby_id>/preventive-events/", views.baby_preventive_events),
    path("baby/profiles/<uuid:baby_id>/appointment-questions/", views.baby_appointment_question),
    path("baby/profiles/<uuid:baby_id>/handover/", views.baby_handover),
    path("baby/handover/<uuid:handover_id>/", views.baby_handover_detail),
    path("baby/profiles/<uuid:baby_id>/cockpit/", views.baby_cockpit),
    path("baby/profiles/<uuid:baby_id>/report/", views.baby_report),
    path("baby/media/", media_views.private_media_upload),
    path("baby/media/<uuid:media_id>/", media_views.private_media_detail),
]
