from decimal import Decimal

from django.db import transaction
from rest_framework import serializers, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from entitlements.services import require_capability
from family.models import Family
from .commitment_models import BudgetCommitment
from .commitment_services import consume_budget_commitment, release_budget_commitment, upsert_budget_commitment
from .models import Expense
from .serializers import ExpenseSerializer


class CommitmentWriteSerializer(serializers.Serializer):
    family = serializers.UUIDField()
    ledger = serializers.UUIDField()
    budget = serializers.UUIDField(required=False, allow_null=True)
    amount = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0.01"))


class CommitmentConsumeSerializer(serializers.Serializer):
    family = serializers.UUIDField()
    expense = serializers.UUIDField()
    budget = serializers.UUIDField(required=False, allow_null=True)


class CommitmentPurchaseSerializer(serializers.Serializer):
    family = serializers.UUIDField()
    budget = serializers.UUIDField(required=False, allow_null=True)
    expense = serializers.DictField()


def _family(request, family_id):
    family = Family.objects.filter(id=family_id, memberships__user=request.user, status=Family.Status.ACTIVE).first()
    if not family:
        raise PermissionDenied("Familie ist für diesen Benutzer nicht verfügbar.")
    require_capability(request.user, family, "expenses")
    return family


def _payload(row):
    return {
        "id": str(row.id),
        "family": str(row.family_id),
        "ledger": str(row.ledger_id),
        "budget": str(row.budget_id) if row.budget_id else None,
        "source_type": row.source_type,
        "source_id": str(row.source_id),
        "amount": str(row.amount),
        "currency": row.currency,
        "status": row.status,
        "consumed_by": str(row.consumed_by_id) if row.consumed_by_id else None,
        "released_at": row.released_at,
        "consumed_at": row.consumed_at,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _active_source_commitment(family, source_type, source_id):
    return BudgetCommitment.objects.select_related("ledger", "budget").filter(
        family=family,
        source_type=source_type,
        source_id=source_id,
        status=BudgetCommitment.Status.ACTIVE,
    ).first()


@api_view(["GET", "PUT", "DELETE"])
@permission_classes([IsAuthenticated])
def budget_commitment_source(request, source_type, source_id):
    family_id = request.query_params.get("family") or request.data.get("family")
    if not family_id:
        raise ValidationError({"family": "Familie ist erforderlich."})
    family = _family(request, family_id)

    if request.method == "GET":
        row = _active_source_commitment(family, source_type, source_id)
        return Response({"commitment": _payload(row) if row else None})

    if request.method == "DELETE":
        row = _active_source_commitment(family, source_type, source_id)
        if row is None:
            return Response({"commitment": None})
        return Response({"commitment": _payload(release_budget_commitment(row))})

    serializer = CommitmentWriteSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    if str(serializer.validated_data["family"]) != str(family.id):
        raise ValidationError({"family": "Familie stimmt nicht mit dem Request-Kontext überein."})
    try:
        row = upsert_budget_commitment(
            user=request.user,
            family=family,
            source_type=source_type,
            source_id=source_id,
            ledger_id=serializer.validated_data["ledger"],
            budget_id=serializer.validated_data.get("budget"),
            amount=serializer.validated_data["amount"],
        )
    except ValueError as exc:
        raise ValidationError({"commitment": str(exc)}) from exc
    return Response({"commitment": _payload(row)})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def budget_commitment_consume(request, commitment_id):
    serializer = CommitmentConsumeSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    family = _family(request, serializer.validated_data["family"])
    row = BudgetCommitment.objects.select_related("family", "ledger").filter(id=commitment_id, family=family).first()
    if not row:
        raise NotFound()
    expense = Expense.objects.filter(id=serializer.validated_data["expense"], family=family).first()
    if not expense:
        raise NotFound()
    try:
        row = consume_budget_commitment(
            commitment=row,
            expense=expense,
            budget_id=serializer.validated_data.get("budget"),
        )
    except ValueError as exc:
        raise ValidationError({"commitment": str(exc)}) from exc
    return Response({"commitment": _payload(row)})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@transaction.atomic
def budget_commitment_purchase(request, commitment_id):
    """Create the actual expense and consume its reservation in one DB transaction."""
    serializer = CommitmentPurchaseSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    family = _family(request, serializer.validated_data["family"])
    row = (
        BudgetCommitment.objects.select_for_update()
        .select_related("family", "ledger", "consumed_by")
        .filter(id=commitment_id, family=family)
        .first()
    )
    if not row:
        raise NotFound()

    # The commitment itself is the idempotency boundary. A retried request
    # after a lost response returns the already committed expense rather than
    # posting a second purchase.
    if row.status == BudgetCommitment.Status.CONSUMED:
        if not row.consumed_by_id:
            raise ValidationError({"commitment": "Die bereits verbrauchte Vormerkung hat keine zugehörige Ausgabe mehr."})
        return Response(
            {
                "commitment": _payload(row),
                "expense": ExpenseSerializer(row.consumed_by, context={"request": request}).data,
            }
        )
    if row.status != BudgetCommitment.Status.ACTIVE:
        raise ValidationError({"commitment": "Diese Vormerkung ist nicht mehr aktiv."})

    expense_data = dict(serializer.validated_data["expense"])
    supplied_family = expense_data.get("family")
    if supplied_family and str(supplied_family) != str(family.id):
        raise ValidationError({"expense": {"family": "Ausgabe und Vormerkung müssen derselben Familie gehören."}})
    supplied_ledger = expense_data.get("ledger")
    if supplied_ledger and str(supplied_ledger) != str(row.ledger_id):
        raise ValidationError({"expense": {"ledger": "Ausgabe und Vormerkung müssen denselben Abrechnungskreis verwenden."}})
    expense_data["family"] = str(family.id)
    expense_data["ledger"] = str(row.ledger_id)

    expense_serializer = ExpenseSerializer(data=expense_data, context={"request": request})
    expense_serializer.is_valid(raise_exception=True)
    expense = expense_serializer.save()
    try:
        row = consume_budget_commitment(
            commitment=row,
            expense=expense,
            budget_id=serializer.validated_data.get("budget"),
        )
    except ValueError as exc:
        raise ValidationError({"commitment": str(exc)}) from exc

    return Response(
        {
            "commitment": _payload(row),
            "expense": ExpenseSerializer(expense, context={"request": request}).data,
        },
        status=status.HTTP_201_CREATED,
    )
