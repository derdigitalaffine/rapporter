from django.db import transaction
from django.utils import timezone

from family.models import Membership, Task
from notifications.services import record_notification

from .models import (
    BattleshipBoard,
    BattleshipShot,
    ConnectFourMove,
    GameMatch,
    GameTaskAssignment,
    QuizQuestion,
    QuizRound,
    RockPaperScissorsRound,
)


FLEET = [5, 4, 3, 3, 2]
RPS_BEATS = {"rock": "scissors", "paper": "rock", "scissors": "paper"}


class GameError(Exception):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


def _language(match):
    return "en" if str(match.family.locale or "").lower().startswith("en") else "de"


def _name(member):
    return member.display_name or member.user.get_username()


def _notify(match, recipient, event_type, de_title, en_title, de_body="", en_body=""):
    english = _language(match) == "en"
    return record_notification(
        recipient=recipient,
        event_type=event_type,
        title=en_title if english else de_title,
        body=en_body if english else de_body,
        resource_url=f"/?page=games&game={match.id}",
    )


def notify_challenge(match):
    _notify(
        match,
        match.opponent,
        "games.challenge",
        "Neue Spiele-Herausforderung",
        "New game challenge",
        f"{_name(match.challenger)} möchte gegen dich spielen.",
        f"{_name(match.challenger)} wants to play against you.",
    )


def notify_started(match):
    _notify(
        match,
        match.challenger,
        "games.started",
        "Spiel gestartet",
        "Game started",
        f"{_name(match.opponent)} hat deine Herausforderung angenommen.",
        f"{_name(match.opponent)} accepted your challenge.",
    )


def notify_turn(match, recipient, *, setup=False):
    _notify(
        match,
        recipient,
        "games.turn",
        "Du bist am Zug" if not setup else "Deine Flotte fehlt noch",
        "Your turn" if not setup else "Place your fleet",
        "Öffne das Spiel und mache deinen nächsten Zug." if not setup else "Öffne das Spiel und bestätige deine Schiffe.",
        "Open the game and make your next move." if not setup else "Open the game and confirm your ships.",
    )


def notify_finished(match):
    for recipient in (match.challenger, match.opponent):
        if match.is_draw:
            de_body, en_body = "Das Spiel endet unentschieden.", "The game ends in a draw."
        elif match.winner_id == recipient.id:
            de_body, en_body = "Du hast gewonnen.", "You won."
        else:
            de_body, en_body = f"{_name(match.winner)} hat gewonnen.", f"{_name(match.winner)} won."
        _notify(match, recipient, "games.finished", "Spiel beendet", "Game finished", de_body, en_body)


def _task_assignment(match):
    return (
        GameTaskAssignment.objects.select_for_update(of=("self",))
        .select_related("task", "expected_assignee", "applied_assignee")
        .filter(match=match)
        .first()
    )


def _task_assignment_is_available(stake, match, *, task=None):
    task = task if task is not None else stake.task
    if task.family_id != match.family_id or task.completed_at:
        return False
    if task.hidden_from_user_id in {match.challenger.user_id, match.opponent.user_id}:
        return False
    return Membership.objects.filter(
        family_id=match.family_id,
        user_id__in=[match.challenger.user_id, match.opponent.user_id],
        user__is_active=True,
    ).count() == 2


def apply_task_assignment(match):
    """Apply a previously consented task stake exactly once after a finished match."""
    stake = _task_assignment(match)
    if not stake or stake.applied_at or stake.invalidated_at:
        return stake

    now = timezone.now()
    if match.status != GameMatch.Status.FINISHED:
        return stake
    if not stake.challenger_confirmed_at or not stake.opponent_confirmed_at:
        stake.invalidated_at = now
        stake.invalidation_reason = "missing_consent"
        stake.save(update_fields=["invalidated_at", "invalidation_reason", "updated_at"])
        return stake
    if match.is_draw or not match.winner_id:
        stake.invalidated_at = now
        stake.invalidation_reason = "draw"
        stake.save(update_fields=["invalidated_at", "invalidation_reason", "updated_at"])
        return stake
    task = Task.objects.select_for_update().get(id=stake.task_id)
    if not _task_assignment_is_available(stake, match, task=task):
        stake.invalidated_at = now
        stake.invalidation_reason = "task_unavailable"
        stake.save(update_fields=["invalidated_at", "invalidation_reason", "updated_at"])
        return stake
    if task.assignee_id != stake.expected_assignee_id:
        stake.invalidated_at = now
        stake.invalidation_reason = "task_assignment_changed"
        stake.save(update_fields=["invalidated_at", "invalidation_reason", "updated_at"])
        return stake

    winner = match.winner
    loser = match.opponent_for(winner)
    selected = winner if stake.rule == GameTaskAssignment.Rule.WINNER else loser
    task.assignee_id = selected.user_id
    task.save(update_fields=["assignee", "updated_at"])
    stake.applied_assignee_id = selected.user_id
    stake.applied_at = now
    stake.save(update_fields=["applied_assignee", "applied_at", "updated_at"])
    return stake


def _finish_match(match, winner=None, *, draw=False):
    match.status = GameMatch.Status.FINISHED
    match.winner = None if draw else winner
    match.is_draw = draw
    match.finished_at = timezone.now()
    match.current_turn = None
    match.save()
    apply_task_assignment(match)
    notify_finished(match)


def ensure_quiz_round(match):
    existing = QuizRound.objects.select_related("question").filter(match=match, number=match.current_round).first()
    if existing:
        return existing
    used = QuizRound.objects.filter(match=match).values_list("question_id", flat=True)
    question = QuizQuestion.objects.filter(mode=match.quiz_mode, active=True).exclude(id__in=used).order_by("id").first()
    if not question:
        raise GameError("quiz_question_unavailable")
    return QuizRound.objects.create(match=match, number=match.current_round, question=question)


def accept_match(match_id, actor, *, task_assignment_confirmed=False):
    with transaction.atomic():
        match = GameMatch.objects.select_for_update().select_related("family", "challenger__user", "opponent__user").get(id=match_id)
        if match.opponent_id != actor.id:
            raise GameError("only_opponent_can_accept")
        if match.status != GameMatch.Status.PENDING:
            raise GameError("match_not_pending")
        if not match.challenger.user.is_active or not match.opponent.user.is_active:
            raise GameError("opponent_unavailable")
        stake = _task_assignment(match)
        if stake:
            if not task_assignment_confirmed:
                raise GameError("task_assignment_consent_required")
            task = Task.objects.select_for_update().get(id=stake.task_id)
            if not _task_assignment_is_available(stake, match, task=task):
                raise GameError("task_assignment_unavailable")
            if task.assignee_id != stake.expected_assignee_id:
                raise GameError("task_assignment_changed")
            stake.opponent_confirmed_at = timezone.now()
            stake.save(update_fields=["opponent_confirmed_at", "updated_at"])
        match.status = GameMatch.Status.ACTIVE
        match.accepted_at = timezone.now()
        if match.game_type == GameMatch.GameType.CONNECT_FOUR:
            match.current_turn = match.challenger
        match.save()
        if match.game_type == GameMatch.GameType.QUIZ:
            ensure_quiz_round(match)
        notify_started(match)
        if match.game_type == GameMatch.GameType.BATTLESHIP:
            notify_turn(match, match.challenger, setup=True)
            notify_turn(match, match.opponent, setup=True)
        elif match.game_type == GameMatch.GameType.CONNECT_FOUR:
            notify_turn(match, match.challenger)
        elif match.game_type == GameMatch.GameType.QUIZ:
            notify_turn(match, match.challenger)
            notify_turn(match, match.opponent)
    return match


def decline_match(match_id, actor):
    with transaction.atomic():
        match = GameMatch.objects.select_for_update().select_related("family", "challenger__user", "opponent__user").get(id=match_id)
        if match.opponent_id != actor.id:
            raise GameError("only_opponent_can_decline")
        if match.status != GameMatch.Status.PENDING:
            raise GameError("match_not_pending")
        match.status = GameMatch.Status.DECLINED
        match.finished_at = timezone.now()
        match.save()
    return match


def cancel_match(match_id, actor):
    with transaction.atomic():
        match = GameMatch.objects.select_for_update().get(id=match_id)
        if match.challenger_id != actor.id:
            raise GameError("only_challenger_can_cancel")
        if match.status != GameMatch.Status.PENDING:
            raise GameError("match_not_pending")
        match.status = GameMatch.Status.CANCELLED
        match.finished_at = timezone.now()
        match.save()
    return match


def submit_rps_choice(match_id, actor, choice):
    if choice not in RockPaperScissorsRound.Choice.values:
        raise GameError("invalid_choice")
    with transaction.atomic():
        match = GameMatch.objects.select_for_update().select_related("family", "challenger__user", "opponent__user").get(id=match_id)
        if actor.id not in match.participant_ids():
            raise GameError("match_unavailable")
        if match.game_type != GameMatch.GameType.RPS or match.status != GameMatch.Status.ACTIVE:
            raise GameError("rps_not_active")
        round_row, _ = RockPaperScissorsRound.objects.select_for_update().get_or_create(match=match, number=match.current_round)
        field = "challenger_choice" if actor.id == match.challenger_id else "opponent_choice"
        if getattr(round_row, field):
            raise GameError("choice_already_submitted")
        setattr(round_row, field, choice)
        round_row.save()
        other = match.opponent if actor.id == match.challenger_id else match.challenger
        if not round_row.challenger_choice or not round_row.opponent_choice:
            notify_turn(match, other)
            return match

        if round_row.challenger_choice == round_row.opponent_choice:
            round_row.winner = None
        elif RPS_BEATS[round_row.challenger_choice] == round_row.opponent_choice:
            round_row.winner = match.challenger
        else:
            round_row.winner = match.opponent
        round_row.resolved_at = timezone.now()
        round_row.save()

        if match.current_round >= match.rps_round_count:
            challenger_wins = RockPaperScissorsRound.objects.filter(match=match, winner=match.challenger).count()
            opponent_wins = RockPaperScissorsRound.objects.filter(match=match, winner=match.opponent).count()
            if challenger_wins == opponent_wins:
                _finish_match(match, draw=True)
            else:
                _finish_match(match, match.challenger if challenger_wins > opponent_wins else match.opponent)
        else:
            match.current_round += 1
            match.save()
            notify_turn(match, match.challenger)
            notify_turn(match, match.opponent)
    return match


def submit_quiz_answer(match_id, actor, answer_index):
    if isinstance(answer_index, bool) or not isinstance(answer_index, int):
        raise GameError("invalid_quiz_answer")
    with transaction.atomic():
        match = GameMatch.objects.select_for_update().select_related("family", "challenger__user", "opponent__user").get(id=match_id)
        if actor.id not in match.participant_ids():
            raise GameError("match_unavailable")
        if match.game_type != GameMatch.GameType.QUIZ or match.status != GameMatch.Status.ACTIVE:
            raise GameError("quiz_not_active")
        round_row = ensure_quiz_round(match)
        option_count = len(round_row.question.options_de or [])
        if answer_index < 0 or answer_index >= option_count:
            raise GameError("invalid_quiz_answer")
        field = "challenger_answer" if actor.id == match.challenger_id else "opponent_answer"
        if getattr(round_row, field) is not None:
            raise GameError("answer_already_submitted")
        setattr(round_row, field, answer_index)
        round_row.save(update_fields=[field, "updated_at"])
        other = match.opponent_for(actor)
        if round_row.challenger_answer is None or round_row.opponent_answer is None:
            notify_turn(match, other)
            return match

        round_row.challenger_correct = round_row.challenger_answer == round_row.question.correct_index
        round_row.opponent_correct = round_row.opponent_answer == round_row.question.correct_index
        round_row.resolved_at = timezone.now()
        round_row.save(update_fields=["challenger_correct", "opponent_correct", "resolved_at", "updated_at"])

        if match.current_round >= match.quiz_round_count:
            challenger_score = QuizRound.objects.filter(match=match, challenger_correct=True).count()
            opponent_score = QuizRound.objects.filter(match=match, opponent_correct=True).count()
            if challenger_score == opponent_score:
                _finish_match(match, draw=True)
            else:
                _finish_match(match, match.challenger if challenger_score > opponent_score else match.opponent)
        else:
            match.current_round += 1
            match.save(update_fields=["current_round", "updated_at"])
            ensure_quiz_round(match)
            notify_turn(match, match.challenger)
            notify_turn(match, match.opponent)
    return match


def normalize_fleet(ships):
    if not isinstance(ships, list) or len(ships) != len(FLEET):
        raise GameError("invalid_fleet")
    normalized = []
    occupied = set()
    lengths = []
    for ship in ships:
        cells = ship.get("cells") if isinstance(ship, dict) else None
        if not isinstance(cells, list) or not cells:
            raise GameError("invalid_fleet")
        parsed = []
        for cell in cells:
            if not isinstance(cell, list) or len(cell) != 2 or any(isinstance(v, bool) or not isinstance(v, int) for v in cell):
                raise GameError("invalid_fleet")
            x, y = cell
            if not 0 <= x <= 9 or not 0 <= y <= 9 or (x, y) in occupied:
                raise GameError("invalid_fleet")
            parsed.append((x, y))
        xs, ys = {x for x, _ in parsed}, {y for _, y in parsed}
        if len(xs) != 1 and len(ys) != 1:
            raise GameError("invalid_fleet")
        axis = sorted(y for _, y in parsed) if len(xs) == 1 else sorted(x for x, _ in parsed)
        if axis != list(range(axis[0], axis[0] + len(axis))):
            raise GameError("invalid_fleet")
        occupied.update(parsed)
        lengths.append(len(parsed))
        normalized.append({"cells": [[x, y] for x, y in sorted(parsed)]})
    if sorted(lengths, reverse=True) != FLEET:
        raise GameError("invalid_fleet")
    return normalized


def submit_fleet(match_id, actor, ships):
    fleet = normalize_fleet(ships)
    with transaction.atomic():
        match = GameMatch.objects.select_for_update().select_related("family", "challenger__user", "opponent__user").get(id=match_id)
        if actor.id not in match.participant_ids():
            raise GameError("match_unavailable")
        if match.game_type != GameMatch.GameType.BATTLESHIP or match.status != GameMatch.Status.ACTIVE:
            raise GameError("battleship_not_active")
        board, _ = BattleshipBoard.objects.select_for_update().get_or_create(match=match, player=actor)
        if board.confirmed:
            raise GameError("fleet_already_confirmed")
        board.ships = fleet
        board.confirmed = True
        board.save()
        other = match.opponent_for(actor)
        other_board = BattleshipBoard.objects.filter(match=match, player=other, confirmed=True).first()
        if other_board:
            match.current_turn = match.challenger
            match.save()
            notify_turn(match, match.challenger)
        else:
            notify_turn(match, other, setup=True)
    return match


def fire_shot(match_id, actor, x, y):
    if any(isinstance(v, bool) or not isinstance(v, int) for v in (x, y)) or not 0 <= x <= 9 or not 0 <= y <= 9:
        raise GameError("invalid_coordinate")
    with transaction.atomic():
        match = GameMatch.objects.select_for_update().select_related("family", "challenger__user", "opponent__user").get(id=match_id)
        if actor.id not in match.participant_ids():
            raise GameError("match_unavailable")
        if match.game_type != GameMatch.GameType.BATTLESHIP or match.status != GameMatch.Status.ACTIVE:
            raise GameError("battleship_not_active")
        if match.current_turn_id != actor.id:
            raise GameError("not_your_turn")
        target = match.opponent_for(actor)
        board = BattleshipBoard.objects.filter(match=match, player=target, confirmed=True).first()
        own_board = BattleshipBoard.objects.filter(match=match, player=actor, confirmed=True).first()
        if not board or not own_board:
            raise GameError("fleets_not_ready")
        if BattleshipShot.objects.filter(match=match, target=target, x=x, y=y).exists():
            raise GameError("coordinate_already_fired")

        point = [x, y]
        ship = next((row for row in board.ships if point in row.get("cells", [])), None)
        prior_hits = {
            (shot.x, shot.y)
            for shot in BattleshipShot.objects.filter(match=match, target=target).exclude(result=BattleshipShot.Result.MISS)
        }
        hit_points = prior_hits | ({(x, y)} if ship else set())
        result = BattleshipShot.Result.MISS
        ship_size = None
        if ship:
            ship_cells = {tuple(cell) for cell in ship["cells"]}
            ship_size = len(ship_cells)
            result = BattleshipShot.Result.SUNK if ship_cells <= hit_points else BattleshipShot.Result.HIT
        sequence = BattleshipShot.objects.filter(match=match).count() + 1
        BattleshipShot.objects.create(
            match=match,
            shooter=actor,
            target=target,
            x=x,
            y=y,
            result=result,
            ship_size=ship_size if result == BattleshipShot.Result.SUNK else None,
            sequence=sequence,
        )
        all_cells = {tuple(cell) for row in board.ships for cell in row.get("cells", [])}
        if ship and all_cells <= hit_points:
            _finish_match(match, actor)
        else:
            match.current_turn = target
            match.save()
            notify_turn(match, target)
    return match


def _connect_four_winner(moves, player_id, column, row):
    occupied = {(move.column, move.row) for move in moves if move.player_id == player_id}
    occupied.add((column, row))
    for dx, dy in ((1, 0), (0, 1), (1, 1), (1, -1)):
        run = 1
        for direction in (-1, 1):
            x, y = column + dx * direction, row + dy * direction
            while (x, y) in occupied:
                run += 1
                x += dx * direction
                y += dy * direction
        if run >= 4:
            return True
    return False


def drop_connect_four(match_id, actor, column):
    if isinstance(column, bool) or not isinstance(column, int) or not 0 <= column <= 6:
        raise GameError("invalid_column")
    with transaction.atomic():
        match = GameMatch.objects.select_for_update().select_related("family", "challenger__user", "opponent__user").get(id=match_id)
        if actor.id not in match.participant_ids():
            raise GameError("match_unavailable")
        if match.game_type != GameMatch.GameType.CONNECT_FOUR or match.status != GameMatch.Status.ACTIVE:
            raise GameError("connect_four_not_active")
        if match.current_turn_id != actor.id:
            raise GameError("not_your_turn")
        moves = list(ConnectFourMove.objects.select_for_update().filter(match=match))
        used_rows = {move.row for move in moves if move.column == column}
        row = next((candidate for candidate in range(5, -1, -1) if candidate not in used_rows), None)
        if row is None:
            raise GameError("column_full")
        sequence = len(moves) + 1
        ConnectFourMove.objects.create(match=match, player=actor, column=column, row=row, sequence=sequence)
        if _connect_four_winner(moves, actor.id, column, row):
            _finish_match(match, actor)
        elif sequence >= 42:
            _finish_match(match, draw=True)
        else:
            target = match.opponent_for(actor)
            match.current_turn = target
            match.save(update_fields=["current_turn", "updated_at"])
            notify_turn(match, target)
    return match
