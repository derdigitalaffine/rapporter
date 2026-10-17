import secrets

from django.db import transaction
from django.utils import timezone

from family.models import Membership
from games.models import GameMatch
from games.services import notify_challenge

from .models import Decision, DecisionOption, DecisionTieBreak, DecisionVote


class DecisionTieBreakError(Exception):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


def _can_manage(decision, membership):
    return decision.created_by_id == membership.user_id or membership.role in {
        Membership.Role.OWNER,
        Membership.Role.ADULT,
    }


def _option_rows(decision):
    rows = []
    for option in DecisionOption.objects.filter(decision=decision).prefetch_related("votes"):
        votes = list(option.votes.all())
        ranks = [vote.rank for vote in votes if vote.rank is not None]
        scores = [vote.score for vote in votes if vote.score is not None]
        rows.append(
            (
                option,
                {
                    "votes": len(votes),
                    "average_rank": round(sum(ranks) / len(ranks), 2) if ranks else None,
                    "average_score": round(sum(scores) / len(scores), 2) if scores else None,
                },
            )
        )
    return rows


def leader_options(decision):
    rows = _option_rows(decision)
    if decision.mode == Decision.Mode.RANKING:
        candidates = [(payload["average_rank"], option) for option, payload in rows if payload["average_rank"] is not None]
        if not candidates:
            return []
        best = min(value for value, _ in candidates)
    elif decision.mode == Decision.Mode.RATING:
        candidates = [(payload["average_score"], option) for option, payload in rows if payload["average_score"] is not None]
        if not candidates:
            return []
        best = max(value for value, _ in candidates)
    else:
        candidates = [(payload["votes"], option) for option, payload in rows]
        best = max((value for value, _ in candidates), default=0)
        if best <= 0:
            return []
    return [option for value, option in candidates if value == best]


def _preferred_leader(decision, member_id, leader_ids):
    votes = list(DecisionVote.objects.filter(decision=decision, member_id=member_id, option_id__in=leader_ids))
    if decision.mode in {Decision.Mode.SINGLE, Decision.Mode.MULTIPLE}:
        return votes[0].option_id if len(votes) == 1 else None
    if decision.mode == Decision.Mode.RANKING:
        ranked = [vote for vote in votes if vote.rank is not None]
        if not ranked:
            return None
        best = min(vote.rank for vote in ranked)
        preferred = [vote.option_id for vote in ranked if vote.rank == best]
        return preferred[0] if len(preferred) == 1 else None
    if decision.mode == Decision.Mode.RATING:
        rated = [vote for vote in votes if vote.score is not None]
        if not rated:
            return None
        best = max(vote.score for vote in rated)
        preferred = [vote.option_id for vote in rated if vote.score == best]
        return preferred[0] if len(preferred) == 1 else None
    return None


def game_mapping(decision, leaders=None):
    if decision.anonymous:
        return None
    leaders = list(leaders if leaders is not None else leader_options(decision))
    if len(leaders) != 2:
        return None
    member_ids = list(
        DecisionVote.objects.filter(decision=decision)
        .values_list("member_id", flat=True)
        .distinct()
    )
    if len(member_ids) != 2:
        return None
    members = list(
        Membership.objects.select_related("user")
        .filter(id__in=member_ids, family=decision.family, user__is_active=True)
    )
    if len(members) != 2:
        return None
    leader_ids = {row.id for row in leaders}
    mapping = {member.id: _preferred_leader(decision, member.id, leader_ids) for member in members}
    if any(option_id is None for option_id in mapping.values()):
        return None
    if set(mapping.values()) != leader_ids:
        return None
    return {member.id: (member, DecisionOption.objects.get(id=mapping[member.id])) for member in members}


def _resolution_payload(tie_break):
    if not tie_break or not tie_break.resolved_at or not tie_break.winner_option_id:
        return None
    return {
        "method": tie_break.method,
        "winner": {
            "id": str(tie_break.winner_option_id),
            "label": tie_break.winner_option.label,
        },
        "resolved_at": tie_break.resolved_at,
    }


def decorate_result(decision, membership, raw_result):
    try:
        tie_break = decision.tie_break
    except DecisionTieBreak.DoesNotExist:
        tie_break = None
    resolution = _resolution_payload(tie_break)
    raw_result["resolution"] = resolution
    available = not decision.is_open and raw_result.get("is_tie") and resolution is None
    leaders = []
    if available:
        leader_ids = {row.get("id") for row in raw_result.get("leaders", [])}
        leaders = list(DecisionOption.objects.filter(decision=decision, id__in=leader_ids))
    mapping = game_mapping(decision, leaders) if available and not tie_break else None
    game = tie_break.game_match if tie_break and tie_break.game_match_id else None
    raw_result["tie_break"] = {
        "available": bool(available),
        "can_random": bool(available and _can_manage(decision, membership) and not (game and game.status in {GameMatch.Status.PENDING, GameMatch.Status.ACTIVE})),
        "can_game": bool(available and mapping and membership.id in mapping and tie_break is None),
        "game_eligible": bool(available and mapping),
        "game": {
            "id": str(game.id),
            "status": game.status,
            "is_draw": game.is_draw,
            "deep_link": f"/?page=games&family={decision.family_id}&game={game.id}",
        } if game else None,
    }
    return raw_result


def start_tie_break(*, decision_id, family, membership, method, game_type=None):
    if method not in DecisionTieBreak.Method.values:
        raise DecisionTieBreakError("invalid_tie_break_method")
    with transaction.atomic():
        decision = Decision.objects.select_for_update().get(id=decision_id, family=family)
        if decision.is_open:
            raise DecisionTieBreakError("decision_still_open")
        leaders = leader_options(decision)
        if len(leaders) < 2:
            raise DecisionTieBreakError("decision_not_tied")
        tie_break = DecisionTieBreak.objects.select_for_update().filter(decision=decision).select_related("game_match", "winner_option").first()
        if tie_break and tie_break.resolved_at:
            return tie_break

        if method == DecisionTieBreak.Method.RANDOM:
            if not _can_manage(decision, membership):
                raise DecisionTieBreakError("tie_break_forbidden")
            if tie_break and tie_break.game_match and tie_break.game_match.status in {GameMatch.Status.PENDING, GameMatch.Status.ACTIVE}:
                raise DecisionTieBreakError("tie_break_game_active")
            winner = secrets.choice(leaders)
            if tie_break is None:
                tie_break = DecisionTieBreak.objects.create(
                    decision=decision,
                    method=DecisionTieBreak.Method.RANDOM,
                    winner_option=winner,
                    created_by=membership.user,
                    resolved_at=timezone.now(),
                )
            else:
                tie_break.method = DecisionTieBreak.Method.RANDOM
                tie_break.winner_option = winner
                tie_break.resolved_at = timezone.now()
                tie_break.save(update_fields=["method", "winner_option", "resolved_at", "updated_at"])
            return tie_break

        if tie_break is not None:
            return tie_break
        mapping = game_mapping(decision, leaders)
        if not mapping or membership.id not in mapping:
            raise DecisionTieBreakError("game_tie_break_unavailable")
        if game_type not in GameMatch.GameType.values:
            raise DecisionTieBreakError("invalid_game_type")
        challenger, challenger_option = mapping[membership.id]
        other_id = next(member_id for member_id in mapping if member_id != membership.id)
        opponent, opponent_option = mapping[other_id]
        round_count = 1 if game_type in {GameMatch.GameType.BATTLESHIP, GameMatch.GameType.CONNECT_FOUR} else 3
        match = GameMatch.objects.create(
            family=family,
            challenger=challenger,
            opponent=opponent,
            game_type=game_type,
            rps_round_count=round_count if game_type == GameMatch.GameType.RPS else 3,
            quiz_round_count=5,
        )
        tie_break = DecisionTieBreak.objects.create(
            decision=decision,
            method=DecisionTieBreak.Method.GAME,
            game_match=match,
            challenger_option=challenger_option,
            opponent_option=opponent_option,
            created_by=membership.user,
        )
        notify_challenge(match)
        return tie_break


def resolve_game_tie_break(match):
    if match.status != GameMatch.Status.FINISHED or match.is_draw or not match.winner_id:
        return None
    tie_break = (
        DecisionTieBreak.objects.select_for_update()
        .filter(game_match=match, resolved_at__isnull=True)
        .select_related("challenger_option", "opponent_option")
        .first()
    )
    if not tie_break:
        return None
    if match.winner_id == match.challenger_id:
        winner = tie_break.challenger_option
    elif match.winner_id == match.opponent_id:
        winner = tie_break.opponent_option
    else:
        return None
    if not winner:
        return None
    tie_break.winner_option = winner
    tie_break.resolved_at = timezone.now()
    tie_break.save(update_fields=["winner_option", "resolved_at", "updated_at"])
    return tie_break
