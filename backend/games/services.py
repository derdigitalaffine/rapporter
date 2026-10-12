from django.db import transaction
from django.utils import timezone

from notifications.services import record_notification

from .models import BattleshipBoard, BattleshipShot, GameMatch, RockPaperScissorsRound


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


def accept_match(match_id, actor):
    with transaction.atomic():
        match = GameMatch.objects.select_for_update().select_related("family", "challenger__user", "opponent__user").get(id=match_id)
        if match.opponent_id != actor.id:
            raise GameError("only_opponent_can_accept")
        if match.status != GameMatch.Status.PENDING:
            raise GameError("match_not_pending")
        match.status = GameMatch.Status.ACTIVE
        match.accepted_at = timezone.now()
        match.save()
        notify_started(match)
        if match.game_type == GameMatch.GameType.BATTLESHIP:
            notify_turn(match, match.challenger, setup=True)
            notify_turn(match, match.opponent, setup=True)
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
            match.status = GameMatch.Status.FINISHED
            match.finished_at = timezone.now()
            if challenger_wins == opponent_wins:
                match.is_draw = True
                match.winner = None
            else:
                match.is_draw = False
                match.winner = match.challenger if challenger_wins > opponent_wins else match.opponent
            match.save()
            notify_finished(match)
        else:
            match.current_round += 1
            match.save()
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
            match.status = GameMatch.Status.FINISHED
            match.winner = actor
            match.is_draw = False
            match.finished_at = timezone.now()
            match.current_turn = None
            match.save()
            notify_finished(match)
        else:
            match.current_turn = target
            match.save()
            notify_turn(match, target)
    return match
