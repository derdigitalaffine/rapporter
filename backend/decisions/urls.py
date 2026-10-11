from django.urls import path

from .views import decision_close, decision_detail, decision_list, decision_vote


urlpatterns = [
    path("decisions/", decision_list, name="decision-list"),
    path("decisions/<uuid:decision_id>/", decision_detail, name="decision-detail"),
    path("decisions/<uuid:decision_id>/vote/", decision_vote, name="decision-vote"),
    path("decisions/<uuid:decision_id>/close/", decision_close, name="decision-close"),
]
