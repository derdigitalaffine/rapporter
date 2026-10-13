"""Identity adapter for the existing game engines; family seats remain Memberships."""
from dataclasses import dataclass

from django.http import Http404

from messenger.access import friendship_access, preferences, require_writer


@dataclass
class PersonalActor:
    user: object

    @property
    def id(self):
        return f"u:{self.user.pk}"

    @property
    def user_id(self):
        return self.user.pk

    @property
    def display_name(self):
        return preferences(self.user).display_name

    role = "friend"


def player(match, field):
    if match.friendship_id:
        user = getattr(match, field + "_user")
        return PersonalActor(user) if user else None
    return getattr(match, field)


def player_id(row, field):
    user_id = getattr(row, field + "_user_id", None)
    return f"u:{user_id}" if user_id is not None else getattr(row, field + "_id")


def actor_fields(actor, field):
    return {field + "_user": actor.user} if isinstance(actor, PersonalActor) else {field: actor}


def set_player(row, field, actor):
    setattr(row, field, None if isinstance(actor, PersonalActor) else actor)
    if hasattr(row, field + "_user_id"):
        setattr(row, field + "_user", actor.user if isinstance(actor, PersonalActor) else None)


def authorize_personal(match, actor, *, lock=False):
    if not match.friendship_id:
        if isinstance(actor, PersonalActor) or actor.id not in match.participant_ids():
            raise Http404
        return
    if not isinstance(actor, PersonalActor):
        raise Http404
    require_writer(actor.user)
    friend = friendship_access(actor.user, match.friendship_id, lock=lock)
    if {match.challenger_user_id, match.opponent_user_id} != {friend.low_user_id, friend.high_user_id}:
        raise Http404
    require_writer(friend.low_user)
    require_writer(friend.high_user)
