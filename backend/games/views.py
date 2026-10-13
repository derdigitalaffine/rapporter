import uuid

from django.db import transaction
from django.db.models import F, Q
from django.utils import timezone
from .participants import PersonalActor, player, player_id, authorize_personal
from messenger.access import friendship_access, preferences, require_writer
from messenger.views import rate
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from family.models import Family, Membership, Task

from .models import BattleshipBoard, BattleshipShot, GameMatch, GameTaskAssignment
from .services import (
    GameError,
    accept_match,
    cancel_match,
    decline_match,
    drop_connect_four,
    fire_shot,
    notify_challenge,
    submit_fleet,
    submit_quiz_answer,
    submit_rps_choice,
)


class GameApiError(Exception):
    def __init__(self, code, http_status=status.HTTP_400_BAD_REQUEST):
        super().__init__(code)
        self.code = code
        self.http_status = http_status


def _error(exc):
    if isinstance(exc, GameApiError):
        return Response({"code": exc.code}, status=exc.http_status)
    if isinstance(exc, GameError):
        http_status = status.HTTP_404_NOT_FOUND if exc.code == "match_unavailable" else status.HTTP_409_CONFLICT
        return Response({"code": exc.code}, status=http_status)
    if isinstance(exc, GameMatch.DoesNotExist):
        return Response({"code": "match_unavailable"}, status=status.HTTP_404_NOT_FOUND)
    raise exc


def _uuid(value, code):
    try:
        return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))
    except (TypeError, ValueError, AttributeError):
        raise GameApiError(code, status.HTTP_404_NOT_FOUND) from None


def _membership(user, family_id):
    parsed = _uuid(family_id, "family_unavailable")
    member = (
        Membership.objects.select_related("family", "user")
        .filter(user=user, user__is_active=True, family_id=parsed, family__status=Family.Status.ACTIVE)
        .first()
    )
    if not member:
        raise GameApiError("family_unavailable", status.HTTP_404_NOT_FOUND)
    return member


def _match_context(user, match_id):
    parsed = _uuid(match_id, "match_unavailable")
    match = _match_queryset(user).filter(id=parsed).first()
    if not match:
        raise GameApiError("match_unavailable", status.HTTP_404_NOT_FOUND)
    if match.friendship_id:
        actor = PersonalActor(user)
        authorize_personal(match, actor)
    else:
        if match.family.status != Family.Status.ACTIVE or user.pk not in {match.challenger.user_id, match.opponent.user_id}:
            raise GameApiError("match_unavailable", status.HTTP_404_NOT_FOUND)
        actor = match.challenger if match.challenger.user_id == user.pk else match.opponent
    return match, actor


def _member(member):
    if not member:
        return None
    return {
        "id": str(member.id),
        "display_name": member.display_name or member.user.get_username(),
        "role": member.role,
    }


def _rps_payload(match, actor):
    rounds = []
    for row in match.rps_rounds.select_related("winner__user").all():
        resolved = bool(row.resolved_at and row.challenger_choice and row.opponent_choice)
        mine = row.challenger_choice if actor.id == player_id(match, "challenger") else row.opponent_choice
        theirs = row.opponent_choice if actor.id == player_id(match, "challenger") else row.challenger_choice
        rounds.append(
            {
                "number": row.number,
                "resolved": resolved,
                "submitted_by_me": bool(mine),
                "opponent_submitted": bool(theirs),
                "my_choice": mine if resolved else None,
                "opponent_choice": theirs if resolved else None,
                "winner": _member(PersonalActor(row.winner_user) if row.winner_user_id else row.winner) if resolved else None,
            }
        )
    return {"round_count": match.rps_round_count, "current_round": match.current_round, "rounds": rounds}


def _quiz_payload(match, actor):
    english = str((match.family.locale if match.family_id else match.locale) or "").lower().startswith("en")
    rounds = []
    my_score = 0
    opponent_score = 0
    for row in match.quiz_rounds.select_related("question").all():
        mine = row.challenger_answer if actor.id == player_id(match, "challenger") else row.opponent_answer
        theirs = row.opponent_answer if actor.id == player_id(match, "challenger") else row.challenger_answer
        my_correct = row.challenger_correct if actor.id == player_id(match, "challenger") else row.opponent_correct
        opponent_correct = row.opponent_correct if actor.id == player_id(match, "challenger") else row.challenger_correct
        resolved = bool(row.resolved_at)
        if my_correct is True:
            my_score += 1
        if opponent_correct is True:
            opponent_score += 1
        question = row.question
        payload = {
            "number": row.number,
            "resolved": resolved,
            "submitted_by_me": mine is not None,
            "opponent_submitted": theirs is not None,
            "prompt": question.prompt_en if english else question.prompt_de,
            "options": question.options_en if english else question.options_de,
            "my_answer": mine if resolved else None,
            "opponent_answer": theirs if resolved else None,
            "my_correct": my_correct if resolved else None,
            "opponent_correct": opponent_correct if resolved else None,
        }
        if resolved:
            payload["correct_answer"] = question.correct_index
            payload["explanation"] = question.explanation_en if english else question.explanation_de
        rounds.append(payload)
    current = next((row for row in rounds if row["number"] == match.current_round), None)
    return {
        "mode": match.quiz_mode,
        "round_count": match.quiz_round_count,
        "current_round": match.current_round,
        "my_score": my_score,
        "opponent_score": opponent_score,
        "needs_answer": match.status == GameMatch.Status.ACTIVE and bool(current) and not current["submitted_by_me"],
        "rounds": rounds,
    }


def _battleship_payload(match, actor):
    boards = {player_id(row, "player"): row for row in match.battleship_boards.all()}
    mine = boards.get(actor.id)
    opponent = player(match, "opponent") if actor.id == player_id(match, "challenger") else player(match, "challenger")
    theirs = boards.get(opponent.id)
    shots = [
        {
            "x": row.x,
            "y": row.y,
            "result": row.result,
            "ship_size": row.ship_size,
            "sequence": row.sequence,
            "mine": player_id(row, "shooter") == actor.id,
        }
        for row in match.battleship_shots.all()
    ]
    if match.status != GameMatch.Status.ACTIVE:
        phase = "finished" if match.status == GameMatch.Status.FINISHED else match.status
    elif not (mine and mine.confirmed and theirs and theirs.confirmed):
        phase = "setup"
    else:
        phase = "play"
    return {
        "phase": phase,
        "my_fleet_confirmed": bool(mine and mine.confirmed),
        "opponent_fleet_confirmed": bool(theirs and theirs.confirmed),
        "my_ships": mine.ships if mine and mine.confirmed else [],
        "shots": shots,
    }


def _connect_four_payload(match, actor):
    moves = [
        {
            "column": move.column,
            "row": move.row,
            "sequence": move.sequence,
            "mine": player_id(move, "player") == actor.id,
        }
        for move in match.connect_four_moves.all()
    ]
    return {"columns": 7, "rows": 6, "moves": moves}


def _task_assignment_payload(match):
    if match.friendship_id:
        return None
    stake = getattr(match, "task_assignment", None)
    if not stake:
        return None
    if stake.applied_at:
        outcome = "applied"
    elif stake.invalidated_at:
        outcome = "draw" if stake.invalidation_reason == "draw" else "invalidated"
    elif stake.opponent_confirmed_at:
        outcome = "ready"
    else:
        outcome = "pending_consent"
    return {
        "task": {
            "id": str(stake.task_id),
            "title": stake.task.title,
            "assignee_user_id": stake.task.assignee_id,
        },
        "rule": stake.rule,
        "challenger_confirmed": bool(stake.challenger_confirmed_at),
        "opponent_confirmed": bool(stake.opponent_confirmed_at),
        "outcome": outcome,
        "applied_assignee_user_id": stake.applied_assignee_id,
        "invalidation_reason": stake.invalidation_reason or None,
    }


def _serialize(match, actor):
    payload = {
        "id": str(match.id),
        "family": str(match.family_id) if match.family_id else None,
        "friendship_id": str(match.friendship_id) if match.friendship_id else None,
        "game_type": match.game_type,
        "status": match.status,
        "challenger": _member(player(match, "challenger")),
        "opponent": _member(player(match, "opponent")),
        "winner": _member(player(match, "winner")),
        "is_draw": match.is_draw,
        "current_turn": _member(player(match, "current_turn")),
        "is_my_turn": player_id(match, "current_turn") == actor.id,
        "am_challenger": player_id(match, "challenger") == actor.id,
        "can_accept": match.status == GameMatch.Status.PENDING and player_id(match, "opponent") == actor.id,
        "can_decline": match.status == GameMatch.Status.PENDING and player_id(match, "opponent") == actor.id,
        "can_cancel": match.status == GameMatch.Status.PENDING and player_id(match, "challenger") == actor.id,
        "created_at": match.created_at,
        "updated_at": match.updated_at,
        "finished_at": match.finished_at,
        "task_assignment": _task_assignment_payload(match),
    }
    if match.game_type == GameMatch.GameType.RPS:
        payload["rps"] = _rps_payload(match, actor)
        if match.status == GameMatch.Status.ACTIVE:
            current = next((row for row in payload["rps"]["rounds"] if row["number"] == match.current_round), None)
            payload["is_my_turn"] = not current or not current["submitted_by_me"]
    elif match.game_type == GameMatch.GameType.BATTLESHIP:
        payload["battleship"] = _battleship_payload(match, actor)
    elif match.game_type == GameMatch.GameType.QUIZ:
        payload["quiz"] = _quiz_payload(match, actor)
        payload["is_my_turn"] = payload["quiz"]["needs_answer"]
    elif match.game_type == GameMatch.GameType.CONNECT_FOUR:
        payload["connect_four"] = _connect_four_payload(match, actor)
    return payload


def _match_queryset(user):
    # A game reference never expands the canonical current Task visibility.
    return GameMatch.objects.exclude(task_assignment__task__hidden_from_user=user).filter(
        Q(task_assignment__isnull=True) | Q(task_assignment__task__family_id=F("family_id"))
    ).select_related(
        "family", "friendship", "challenger_user", "opponent_user", "winner_user", "current_turn_user",
        "challenger__user",
        "opponent__user",
        "winner__user",
        "current_turn__user",
        "task_assignment__task__assignee",
        "task_assignment__applied_assignee",
    ).prefetch_related(
        "rps_rounds__winner__user", "rps_rounds__winner_user",
        "battleship_boards",
        "battleship_shots",
        "quiz_rounds__question",
        "connect_four_moves",
    )


def _fresh(match_id, actor):
    return _serialize(_match_queryset(actor.user).get(id=match_id), actor)


def _create_task_assignment(match, actor, opponent, assignment_data):
    if match.friendship_id:
        raise GameApiError("personal_task_stake_forbidden")
    if not isinstance(assignment_data, dict):
        raise GameApiError("invalid_task_assignment")
    if assignment_data.get("confirmed") is not True:
        raise GameApiError("task_assignment_consent_required", status.HTTP_409_CONFLICT)
    rule = str(assignment_data.get("rule") or "")
    if rule not in GameTaskAssignment.Rule.values:
        raise GameApiError("invalid_task_assignment_rule")
    task_id = _uuid(assignment_data.get("task"), "task_unavailable")
    task = (
        Task.objects.select_for_update()
        .filter(id=task_id, family=actor.family, completed_at__isnull=True)
        .first()
    )
    if not task or task.hidden_from_user_id in {actor.user_id, opponent.user_id}:
        raise GameApiError("task_unavailable", status.HTTP_404_NOT_FOUND)
    return GameTaskAssignment.objects.create(
        match=match,
        task=task,
        rule=rule,
        expected_assignee_id=task.assignee_id,
        challenger_confirmed_at=timezone.now(),
    )


def _personal_match_list(request, friendship_id):
    require_writer(request.user)
    with transaction.atomic():
        friend = friendship_access(request.user, _uuid(friendship_id, "match_unavailable"), lock=request.method == "POST")
        require_writer(friend.low_user)
        require_writer(friend.high_user)
        actor = PersonalActor(request.user)
        if request.method == "GET":
            rows = _match_queryset(request.user).filter(friendship=friend).filter(Q(challenger_user=request.user) | Q(opponent_user=request.user))[:50]
            return Response([_serialize(row, actor) for row in rows])
        rate(request, "chat.write")
        if any(key in request.data for key in ("family", "task_assignment", "opponent")):
            raise GameApiError("personal_task_stake_forbidden")
        game_type = str(request.data.get("game_type") or "")
        if game_type not in GameMatch.GameType.values:
            raise GameApiError("invalid_game_type")
        try:
            count = int(request.data.get("round_count", 5 if game_type == GameMatch.GameType.QUIZ else 3))
        except (ValueError, TypeError):
            raise GameApiError("invalid_round_count") from None
        if (game_type == GameMatch.GameType.RPS and not 1 <= count <= 5) or (game_type == GameMatch.GameType.QUIZ and not 3 <= count <= 7):
            raise GameApiError("invalid_round_count")
        mode = str(request.data.get("quiz_mode") or GameMatch.QuizMode.MIXED)
        if mode not in GameMatch.QuizMode.values:
            raise GameApiError("invalid_quiz_mode")
        match = GameMatch.objects.create(friendship=friend, challenger_user=request.user, opponent_user_id=friend.other_id(request.user.pk), locale=preferences(request.user).locale, game_type=game_type, rps_round_count=count if game_type == GameMatch.GameType.RPS else 3, quiz_round_count=count if game_type == GameMatch.GameType.QUIZ else 5, quiz_mode=mode)
        notify_challenge(match)
        return Response(_fresh(match.pk, actor), status=status.HTTP_201_CREATED)


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def match_list(request):
    try:
        friendship_id = request.data.get("friendship") if request.method == "POST" else request.query_params.get("friendship")
        if friendship_id:
            return _personal_match_list(request, friendship_id)
        if request.method == "POST":
            actor = _membership(request.user, request.data.get("family"))
            opponent_id = _uuid(request.data.get("opponent"), "opponent_unavailable")
            opponent = Membership.objects.select_related("user").filter(id=opponent_id, family=actor.family, user__is_active=True).first()
            if not opponent or opponent.id == actor.id:
                raise GameApiError("opponent_unavailable", status.HTTP_404_NOT_FOUND)
            game_type = str(request.data.get("game_type") or "")
            if game_type not in GameMatch.GameType.values:
                raise GameApiError("invalid_game_type")
            try:
                round_count = int(request.data.get("round_count", 5 if game_type == GameMatch.GameType.QUIZ else 3))
            except (TypeError, ValueError):
                raise GameApiError("invalid_round_count") from None
            if game_type == GameMatch.GameType.RPS and not 1 <= round_count <= 5:
                raise GameApiError("invalid_round_count")
            if game_type == GameMatch.GameType.QUIZ and not 3 <= round_count <= 7:
                raise GameApiError("invalid_round_count")
            quiz_mode = str(request.data.get("quiz_mode") or GameMatch.QuizMode.MIXED)
            if game_type == GameMatch.GameType.QUIZ and quiz_mode not in GameMatch.QuizMode.values:
                raise GameApiError("invalid_quiz_mode")
            if game_type in {GameMatch.GameType.BATTLESHIP, GameMatch.GameType.CONNECT_FOUR}:
                round_count = 1
            assignment_data = request.data.get("task_assignment")
            with transaction.atomic():
                match = GameMatch.objects.create(
                    family=actor.family,
                    challenger=actor,
                    opponent=opponent,
                    game_type=game_type,
                    rps_round_count=round_count if game_type == GameMatch.GameType.RPS else 3,
                    quiz_round_count=round_count if game_type == GameMatch.GameType.QUIZ else 5,
                    quiz_mode=quiz_mode if game_type == GameMatch.GameType.QUIZ else GameMatch.QuizMode.MIXED,
                )
                if assignment_data is not None:
                    _create_task_assignment(match, actor, opponent, assignment_data)
                notify_challenge(match)
            return Response(_fresh(match.id, actor), status=status.HTTP_201_CREATED)

        actor = _membership(request.user, request.query_params.get("family"))
        rows = _match_queryset(request.user).filter(family=actor.family).filter(Q(challenger=actor) | Q(opponent=actor))[:50]
        return Response([_serialize(row, actor) for row in rows])
    except (GameApiError, GameError, GameMatch.DoesNotExist) as exc:
        return _error(exc)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def match_detail(request, match_id):
    try:
        match, actor = _match_context(request.user, match_id)
        return Response(_fresh(match.id, actor))
    except (GameApiError, GameError, GameMatch.DoesNotExist) as exc:
        return _error(exc)


def _action(request, match_id, service):
    try:
        match, actor = _match_context(request.user, match_id)
        if match.friendship_id:
            rate(request, "chat.write")
        service(match.id, actor)
        return Response(_fresh(match.id, actor))
    except (GameApiError, GameError, GameMatch.DoesNotExist) as exc:
        return _error(exc)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def match_accept(request, match_id):
    try:
        match, actor = _match_context(request.user, match_id)
        if match.friendship_id:
            rate(request, "chat.write")
        accept_match(match.id, actor, task_assignment_confirmed=request.data.get("task_assignment_confirmed") is True)
        return Response(_fresh(match.id, actor))
    except (GameApiError, GameError, GameMatch.DoesNotExist) as exc:
        return _error(exc)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def match_decline(request, match_id):
    return _action(request, match_id, decline_match)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def match_cancel(request, match_id):
    return _action(request, match_id, cancel_match)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def rps_choice(request, match_id):
    try:
        match, actor = _match_context(request.user, match_id)
        if match.friendship_id:
            rate(request, "chat.write")
        submit_rps_choice(match.id, actor, str(request.data.get("choice") or ""))
        return Response(_fresh(match.id, actor))
    except (GameApiError, GameError, GameMatch.DoesNotExist) as exc:
        return _error(exc)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def quiz_answer(request, match_id):
    try:
        match, actor = _match_context(request.user, match_id)
        if match.friendship_id:
            rate(request, "chat.write")
        submit_quiz_answer(match.id, actor, request.data.get("answer"))
        return Response(_fresh(match.id, actor))
    except (GameApiError, GameError, GameMatch.DoesNotExist) as exc:
        return _error(exc)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def connect_four_drop(request, match_id):
    try:
        match, actor = _match_context(request.user, match_id)
        if match.friendship_id:
            rate(request, "chat.write")
        drop_connect_four(match.id, actor, request.data.get("column"))
        return Response(_fresh(match.id, actor))
    except (GameApiError, GameError, GameMatch.DoesNotExist) as exc:
        return _error(exc)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def battleship_fleet(request, match_id):
    try:
        match, actor = _match_context(request.user, match_id)
        if match.friendship_id:
            rate(request, "chat.write")
        submit_fleet(match.id, actor, request.data.get("ships"))
        return Response(_fresh(match.id, actor))
    except (GameApiError, GameError, GameMatch.DoesNotExist) as exc:
        return _error(exc)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def battleship_fire(request, match_id):
    try:
        match, actor = _match_context(request.user, match_id)
        if match.friendship_id:
            rate(request, "chat.write")
        fire_shot(match.id, actor, request.data.get("x"), request.data.get("y"))
        return Response(_fresh(match.id, actor))
    except (GameApiError, GameError, GameMatch.DoesNotExist) as exc:
        return _error(exc)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def game_summary(request):
    try:
        actor = _membership(request.user, request.query_params.get("family"))
        rows = (
            _match_queryset(request.user)
            .filter(family=actor.family)
            .filter(Q(challenger=actor) | Q(opponent=actor))
            .filter(status__in=[GameMatch.Status.PENDING, GameMatch.Status.ACTIVE, GameMatch.Status.FINISHED])[:8]
        )
        payloads = [_serialize(row, actor) for row in rows]
        actionable = [row for row in payloads if row["can_accept"] or row["is_my_turn"]]
        if not actionable:
            actionable = [
                row
                for row in payloads
                if row["status"] == GameMatch.Status.ACTIVE
                and row.get("battleship", {}).get("phase") == "setup"
                and not row.get("battleship", {}).get("my_fleet_confirmed", True)
            ]
        return Response({"actionable": actionable[:3], "recent": payloads[:4], "count": len(payloads)})
    except (GameApiError, GameError, GameMatch.DoesNotExist) as exc:
        return _error(exc)
