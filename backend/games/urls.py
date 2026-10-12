from django.urls import path

from .views import (
    battleship_fire,
    battleship_fleet,
    game_summary,
    match_accept,
    match_cancel,
    match_decline,
    match_detail,
    match_list,
    rps_choice,
)


urlpatterns = [
    path("games/", match_list, name="game-list"),
    path("games/summary/", game_summary, name="game-summary"),
    path("games/<uuid:match_id>/", match_detail, name="game-detail"),
    path("games/<uuid:match_id>/accept/", match_accept, name="game-accept"),
    path("games/<uuid:match_id>/decline/", match_decline, name="game-decline"),
    path("games/<uuid:match_id>/cancel/", match_cancel, name="game-cancel"),
    path("games/<uuid:match_id>/rps/choice/", rps_choice, name="game-rps-choice"),
    path("games/<uuid:match_id>/battleship/fleet/", battleship_fleet, name="game-battleship-fleet"),
    path("games/<uuid:match_id>/battleship/fire/", battleship_fire, name="game-battleship-fire"),
]
