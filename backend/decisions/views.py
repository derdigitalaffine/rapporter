import uuid

from django.db import transaction
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from family.context_links import (
    ContextLinkPermissionDenied,
    ContextObjectUnavailable,
    ContextRef,
    InvalidContextReference,
    UnsupportedContextRelation,
    UnsupportedContextType,
    create_context_link,
    default_context_registry,
)
from family.context_models import ContextLink
from family.models import Family, Membership

from .models import Decision, DecisionOption, DecisionVote
from .serializers import DecisionCreateSerializer, DecisionVoteSerializer


class DecisionApiError(Exception):
    def __init__(self, code, http_status=status.HTTP_400_BAD_REQUEST):
        super().__init__(code)
        self.code = code
        self.http_status = http_status


def _error(exc):
    if isinstance(exc, DecisionApiError):
        return Response({"code": exc.code}, status=exc.http_status)
    if isinstance(exc, (UnsupportedContextType, UnsupportedContextRelation, InvalidContextReference)):
        return Response({"code": "invalid_context"}, status=status.HTTP_400_BAD_REQUEST)
    if isinstance(exc, ContextObjectUnavailable):
        return Response({"code": "context_unavailable"}, status=status.HTTP_404_NOT_FOUND)
    if isinstance(exc, ContextLinkPermissionDenied):
        return Response({"code": "context_forbidden"}, status=status.HTTP_403_FORBIDDEN)
    raise exc


def _membership(user, family_id, *, required=True):
    if not family_id:
        if required:
            raise DecisionApiError("family_required")
        return None
    try:
        parsed = family_id if isinstance(family_id, uuid.UUID) else uuid.UUID(str(family_id))
    except (TypeError, ValueError, AttributeError):
        raise DecisionApiError("family_unavailable", status.HTTP_404_NOT_FOUND) from None
    membership = (
        Membership.objects.select_related("family", "user")
        .filter(user=user, family_id=parsed, family__status=Family.Status.ACTIVE)
        .first()
    )
    if not membership:
        raise DecisionApiError("family_unavailable", status.HTTP_404_NOT_FOUND)
    return membership


def _decision_queryset(family):
    return (
        Decision.objects.filter(family=family)
        .select_related("created_by")
        .prefetch_related("options__votes__member__user")
        .order_by("-created_at", "id")
    )


def _context_visibility(user, family, decisions):
    decisions = list(decisions)
    visible_ids = {row.id for row in decisions if not row.context_bound}
    bound_ids = [row.id for row in decisions if row.context_bound]
    contexts = {}
    if not bound_ids:
        return visible_ids, contexts
    links = list(
        ContextLink.objects.filter(
            family=family,
            source_type="decision",
            source_id__in=bound_ids,
            relation_key="decision.context",
        ).order_by("created_at", "id")
    )
    refs = [ContextRef(row.context_type, row.context_id) for row in links]
    resolved = default_context_registry().resolve_many(user, family, refs, strict=False)
    for link in links:
        ref = ContextRef(link.context_type, link.context_id)
        endpoint = resolved.get(ref)
        if endpoint is not None:
            visible_ids.add(link.source_id)
            contexts.setdefault(link.source_id, endpoint)
    return visible_ids, contexts


def _visible_decision(user, family, decision_id):
    try:
        parsed = decision_id if isinstance(decision_id, uuid.UUID) else uuid.UUID(str(decision_id))
    except (TypeError, ValueError, AttributeError):
        raise DecisionApiError("decision_unavailable", status.HTTP_404_NOT_FOUND) from None
    decision = _decision_queryset(family).filter(id=parsed).first()
    if not decision:
        raise DecisionApiError("decision_unavailable", status.HTTP_404_NOT_FOUND)
    visible_ids, contexts = _context_visibility(user, family, [decision])
    if decision.id not in visible_ids:
        raise DecisionApiError("decision_unavailable", status.HTTP_404_NOT_FOUND)
    return decision, contexts.get(decision.id)


def _member_name(member):
    return member.display_name or member.user.get_username()


def _serialize(decision, membership, context=None):
    options = list(decision.options.all())
    selected = []
    voter_ids = set()
    serialized_options = []
    for option in options:
        votes = list(option.votes.all())
        voter_ids.update(vote.member_id for vote in votes)
        mine = any(vote.member_id == membership.id for vote in votes)
        if mine:
            selected.append(str(option.id))
        payload = {
            "id": str(option.id),
            "label": option.label,
            "position": option.position,
            "votes": len(votes),
            "selected_by_me": mine,
        }
        if not decision.anonymous:
            payload["voters"] = [
                {"membership": str(vote.member_id), "name": _member_name(vote.member)} for vote in votes
            ]
        serialized_options.append(payload)
    body = {
        "id": str(decision.id),
        "family": str(decision.family_id),
        "question": decision.question,
        "mode": decision.mode,
        "anonymous": decision.anonymous,
        "closes_at": decision.closes_at,
        "closed_at": decision.closed_at,
        "is_open": decision.is_open,
        "created_at": decision.created_at,
        "options": serialized_options,
        "my_option_ids": selected,
        "total_voters": len(voter_ids),
        "can_vote": membership.role != Membership.Role.GUEST and decision.is_open,
        "can_close": decision.created_by_id == membership.user_id
        or membership.role in {Membership.Role.OWNER, Membership.Role.ADULT},
    }
    if context is not None:
        body["context"] = {
            "type": context.ref.type,
            "id": str(context.ref.id),
            "lifecycle": context.lifecycle,
            "deep_link": context.deep_link,
        }
    else:
        body["context"] = None
    return body


def _fresh(decision_id, family):
    return _decision_queryset(family).get(id=decision_id)


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def decision_list(request):
    try:
        if request.method == "POST":
            serializer = DecisionCreateSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            data = serializer.validated_data
            membership = _membership(request.user, data["family"])
            if membership.role == Membership.Role.GUEST:
                raise DecisionApiError("decision_forbidden", status.HTTP_403_FORBIDDEN)
            context_data = data.get("context")
            with transaction.atomic():
                decision = Decision.objects.create(
                    family=membership.family,
                    question=data["question"],
                    created_by=request.user,
                    mode=data["mode"],
                    anonymous=data["anonymous"],
                    closes_at=data.get("closes_at"),
                    context_bound=False,
                )
                DecisionOption.objects.bulk_create(
                    [
                        DecisionOption(decision=decision, label=label, position=position)
                        for position, label in enumerate(data["options"])
                    ]
                )
                context = None
                if context_data:
                    create_context_link(
                        user=request.user,
                        family=membership.family,
                        source_type="decision",
                        source_id=decision.id,
                        context_type=context_data["type"],
                        context_id=context_data["id"],
                        relation_key="decision.context",
                    )
                    decision.context_bound = True
                    decision.save(update_fields=["context_bound", "updated_at"])
                    ref = ContextRef(context_data["type"], context_data["id"])
                    context = default_context_registry().resolve_many(
                        request.user, membership.family, [ref]
                    ).get(ref)
            decision = _fresh(decision.id, membership.family)
            return Response(_serialize(decision, membership, context), status=status.HTTP_201_CREATED)

        membership = _membership(request.user, request.query_params.get("family"))
        rows = list(_decision_queryset(membership.family)[:100])
        visible_ids, contexts = _context_visibility(request.user, membership.family, rows)
        visible = [row for row in rows if row.id in visible_ids]
        return Response(
            {
                "count": len(visible),
                "results": [_serialize(row, membership, contexts.get(row.id)) for row in visible],
            }
        )
    except (
        DecisionApiError,
        UnsupportedContextType,
        UnsupportedContextRelation,
        InvalidContextReference,
        ContextObjectUnavailable,
        ContextLinkPermissionDenied,
    ) as exc:
        return _error(exc)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def decision_detail(request, decision_id):
    try:
        membership = _membership(request.user, request.query_params.get("family"))
        decision, context = _visible_decision(request.user, membership.family, decision_id)
        return Response(_serialize(decision, membership, context))
    except DecisionApiError as exc:
        return _error(exc)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def decision_vote(request, decision_id):
    serializer = DecisionVoteSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    try:
        membership = _membership(request.user, request.data.get("family"))
        if membership.role == Membership.Role.GUEST:
            raise DecisionApiError("vote_forbidden", status.HTTP_403_FORBIDDEN)
        decision, _ = _visible_decision(request.user, membership.family, decision_id)
        option_ids = serializer.validated_data["option_ids"]
        if decision.mode == Decision.Mode.SINGLE and len(option_ids) > 1:
            raise DecisionApiError("invalid_vote_selection")
        with transaction.atomic():
            locked = Decision.objects.select_for_update().get(id=decision.id, family=membership.family)
            if not locked.is_open:
                raise DecisionApiError("decision_closed", status.HTTP_409_CONFLICT)
            valid_ids = set(
                DecisionOption.objects.filter(decision=locked, id__in=option_ids).values_list("id", flat=True)
            )
            if valid_ids != set(option_ids):
                raise DecisionApiError("invalid_vote_selection")
            DecisionVote.objects.filter(decision=locked, member=membership).delete()
            DecisionVote.objects.bulk_create(
                [DecisionVote(decision=locked, option_id=option_id, member=membership) for option_id in option_ids]
            )
        decision, context = _visible_decision(request.user, membership.family, decision.id)
        return Response(_serialize(decision, membership, context))
    except DecisionApiError as exc:
        return _error(exc)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def decision_close(request, decision_id):
    try:
        membership = _membership(request.user, request.data.get("family"))
        decision, _ = _visible_decision(request.user, membership.family, decision_id)
        can_close = decision.created_by_id == request.user.id or membership.role in {
            Membership.Role.OWNER,
            Membership.Role.ADULT,
        }
        if not can_close:
            raise DecisionApiError("decision_forbidden", status.HTTP_403_FORBIDDEN)
        with transaction.atomic():
            locked = Decision.objects.select_for_update().get(id=decision.id, family=membership.family)
            if locked.closed_at is None:
                locked.closed_at = timezone.now()
                locked.save(update_fields=["closed_at", "updated_at"])
        decision, context = _visible_decision(request.user, membership.family, decision.id)
        return Response(_serialize(decision, membership, context))
    except DecisionApiError as exc:
        return _error(exc)
