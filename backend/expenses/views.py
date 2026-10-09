from django.db import transaction
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from family.models import Family, Membership
from .models import Expense, ReceiptExtraction, Settlement
from .money import balance_summary, simplify_balances
from .ocr import enqueue_receipt_extraction, normalize_receipt_upload
from .serializers import ExpenseSerializer, SettlementSerializer


def _member_payload(row):
    member = row["member"]
    return {
        "id": str(member.id),
        "name": member.display_name or member.user.username,
        "paid": str(row["paid"]),
        "share": str(row["share"]),
        "settled_sent": str(row["settled_sent"]),
        "settled_received": str(row["settled_received"]),
        "balance": str(row["balance"]),
    }


class ExpenseViewSet(viewsets.ModelViewSet):
    serializer_class = ExpenseSerializer

    def get_queryset(self):
        user = self.request.user
        queryset = Expense.objects.select_related("family", "paid_by", "paid_by__user", "created_by", "extraction").prefetch_related("shares", "shares__member", "shares__member__user")
        if not user.is_superuser:
            queryset = queryset.filter(family__memberships__user=user, family__status=Family.Status.ACTIVE)
        family_id = self.request.query_params.get("family")
        if family_id:
            queryset = queryset.filter(family_id=family_id)
        if self.action == "list":
            queryset = queryset.filter(status=Expense.Status.POSTED)
        return queryset.distinct()

    @action(detail=False, methods=["get"])
    def balance(self, request):
        family = self._family(request)
        currency = (request.query_params.get("currency") or "EUR").upper()
        summary = balance_summary(family, currency)
        open_amount = sum((row["balance"] for row in summary.values() if row["balance"] > 0), start=0)
        return Response({
            "family": str(family.id),
            "currency": currency,
            "open_amount": str(open_amount),
            "members": [_member_payload(row) for row in summary.values()],
        })

    @action(detail=False, methods=["get"], url_path="settlement-plan")
    def settlement_plan(self, request):
        family = self._family(request)
        currency = (request.query_params.get("currency") or "EUR").upper()
        summary = balance_summary(family, currency)
        names = {member_id: row["member"].display_name or row["member"].user.username for member_id, row in summary.items()}
        transfers = simplify_balances(summary)
        return Response({
            "family": str(family.id),
            "currency": currency,
            "transfers": [
                {
                    "from_member": item["from"],
                    "from_name": names[item["from"]],
                    "to_member": item["to"],
                    "to_name": names[item["to"]],
                    "amount": str(item["amount"]),
                }
                for item in transfers
            ],
            "disclaimer": "Dokumentiert eine Abrechnung in Rapporter; führt keine reale Zahlung aus.",
        })

    @action(detail=False, methods=["post"], url_path="receipt")
    def upload_receipt(self, request):
        family = self._family(request, from_body=True)
        upload = request.FILES.get("receipt")
        if not upload:
            return Response({"receipt": ["Belegfoto ist erforderlich."]}, status=status.HTTP_400_BAD_REQUEST)
        try:
            content, mime, quality_warnings = normalize_receipt_upload(upload)
        except ValueError as exc:
            return Response({"receipt": [str(exc)]}, status=status.HTTP_400_BAD_REQUEST)

        membership = Membership.objects.filter(family=family, user=request.user).first()
        paid_by = membership
        paid_by_id = request.data.get("paid_by")
        if paid_by_id:
            paid_by = Membership.objects.filter(family=family, id=paid_by_id).first()
            if not paid_by:
                return Response({"paid_by": ["Zahler gehört nicht zu dieser Familie."]}, status=status.HTTP_400_BAD_REQUEST)
        if not paid_by:
            return Response({"paid_by": ["Zahler ist erforderlich."]}, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            expense = Expense.objects.create(
                family=family,
                paid_by=paid_by,
                created_by=request.user,
                source=Expense.Source.RECEIPT,
                status=Expense.Status.DRAFT,
                receipt_status=Expense.ReceiptStatus.QUEUED,
                receipt_content=content,
                receipt_mime=mime,
                currency="EUR",
            )
            extraction = ReceiptExtraction.objects.create(
                expense=expense,
                status=ReceiptExtraction.Status.QUEUED,
                structured_data={"quality_warnings": quality_warnings},
            )
            transaction.on_commit(lambda: enqueue_receipt_extraction(extraction.id))
        data = ExpenseSerializer(expense, context={"request": request}).data
        data["quality_warnings"] = quality_warnings
        return Response(data, status=status.HTTP_202_ACCEPTED)

    @action(detail=True, methods=["post"], url_path="retry-receipt")
    def retry_receipt(self, request, pk=None):
        expense = self.get_object()
        if not expense.receipt_content:
            return Response({"receipt": ["Kein Beleg vorhanden."]}, status=status.HTTP_400_BAD_REQUEST)
        extraction, _ = ReceiptExtraction.objects.get_or_create(expense=expense)
        extraction.status = ReceiptExtraction.Status.QUEUED
        extraction.error = ""
        extraction.processed_at = None
        extraction.save(update_fields=["status", "error", "processed_at", "updated_at"])
        expense.receipt_status = Expense.ReceiptStatus.QUEUED
        expense.save(update_fields=["receipt_status", "updated_at"])
        transaction.on_commit(lambda: enqueue_receipt_extraction(extraction.id))
        return Response({"status": "queued"}, status=status.HTTP_202_ACCEPTED)

    def _family(self, request, from_body=False):
        from rest_framework.exceptions import NotFound, ValidationError
        family_id = request.data.get("family") if from_body else request.query_params.get("family")
        if not family_id:
            raise ValidationError({"family": "Familie ist erforderlich."})
        queryset = Family.objects.filter(id=family_id, status=Family.Status.ACTIVE)
        if not request.user.is_superuser:
            queryset = queryset.filter(memberships__user=request.user)
        family = queryset.distinct().first()
        if not family:
            raise NotFound()
        return family


class SettlementViewSet(viewsets.ModelViewSet):
    serializer_class = SettlementSerializer
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        user = self.request.user
        queryset = Settlement.objects.select_related("family", "from_member", "from_member__user", "to_member", "to_member__user", "created_by")
        if not user.is_superuser:
            queryset = queryset.filter(family__memberships__user=user, family__status=Family.Status.ACTIVE)
        family_id = self.request.query_params.get("family")
        if family_id:
            queryset = queryset.filter(family_id=family_id)
        return queryset.distinct()

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    @action(detail=True, methods=["post"])
    def void(self, request, pk=None):
        settlement = self.get_object()
        if not settlement.voided_at:
            settlement.voided_at = timezone.now()
            settlement.save(update_fields=["voided_at", "updated_at"])
        return Response(self.get_serializer(settlement).data)
