import uuid

from django.db import transaction
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from family.context_links import create_context_link
from family.context_models import ContextLink
from family.models import Family, Membership
from family.travel_models import Trip

from .models import ExpenseLedger, get_default_expense_ledger
from .serializers import ExpenseLedgerSerializer


def _uuid(value):
    try:
        return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))
    except (TypeError, ValueError, AttributeError):
        return None


def _family_membership(user, raw_family_id):
    family_id = _uuid(raw_family_id)
    if not family_id:
        return None, None
    membership = (
        Membership.objects.select_related("family")
        .filter(
            user=user,
            family_id=family_id,
            family__status=Family.Status.ACTIVE,
        )
        .first()
    )
    return (membership.family, membership) if membership else (None, None)


def _linked_ledgers(family, trip):
    links = list(
        ContextLink.objects.filter(
            family=family,
            relation_key="expense.trip",
            source_type="expense_ledger",
            context_type="trip",
            context_id=trip.id,
        ).order_by("created_at", "id")
    )
    if not links:
        return None, False
    ids = [row.source_id for row in links]
    active = (
        ExpenseLedger.objects.filter(family=family, id__in=ids, archived=False)
        .order_by("created_at", "id")
        .first()
    )
    return active, True


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def trip_expense_ledger(request):
    source = request.query_params if request.method == "GET" else request.data
    family, membership = _family_membership(request.user, source.get("family"))
    if not family:
        return Response({"code": "family_unavailable"}, status=status.HTTP_404_NOT_FOUND)

    trip_id = _uuid(source.get("trip"))
    if not trip_id:
        return Response({"code": "invalid_trip"}, status=status.HTTP_400_BAD_REQUEST)

    trip = Trip.objects.filter(family=family, id=trip_id).first()
    if not trip:
        return Response({"code": "trip_unavailable"}, status=status.HTTP_404_NOT_FOUND)

    ledger, has_link = _linked_ledgers(family, trip)
    if ledger:
        return Response(ExpenseLedgerSerializer(ledger, context={"request": request}).data)
    if has_link:
        return Response({"code": "trip_expense_ledger_archived"}, status=status.HTTP_409_CONFLICT)
    if request.method == "GET":
        return Response({"code": "trip_expense_ledger_unavailable"}, status=status.HTTP_404_NOT_FOUND)
    if membership.role not in [Membership.Role.OWNER, Membership.Role.ADULT]:
        return Response({"code": "trip_expense_ledger_forbidden"}, status=status.HTTP_403_FORBIDDEN)
    if trip.archived:
        return Response({"code": "trip_archived"}, status=status.HTTP_409_CONFLICT)

    with transaction.atomic():
        locked_trip = Trip.objects.select_for_update().get(family=family, id=trip.id)
        ledger, has_link = _linked_ledgers(family, locked_trip)
        if ledger:
            return Response(ExpenseLedgerSerializer(ledger, context={"request": request}).data)
        if has_link:
            return Response({"code": "trip_expense_ledger_archived"}, status=status.HTTP_409_CONFLICT)

        default_ledger = get_default_expense_ledger(family)
        ledger = ExpenseLedger.objects.create(
            family=family,
            name=locked_trip.title,
            base_currency=default_ledger.base_currency,
        )
        create_context_link(
            user=request.user,
            family=family,
            source_type="expense_ledger",
            source_id=ledger.id,
            context_type="trip",
            context_id=locked_trip.id,
            relation_key="expense.trip",
        )

    return Response(
        ExpenseLedgerSerializer(ledger, context={"request": request}).data,
        status=status.HTTP_201_CREATED,
    )
