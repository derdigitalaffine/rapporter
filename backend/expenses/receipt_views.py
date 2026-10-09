from django.db import transaction
from django.http import HttpResponse
from django.utils import timezone
from rest_framework.decorators import api_view
from rest_framework.exceptions import NotFound
from rest_framework.response import Response
from rest_framework import status

from family.models import Family
from .models import Expense


@api_view(["GET", "DELETE"])
def receipt_file(request, expense_id):
    queryset = Expense.objects.filter(id=expense_id)
    if not request.user.is_superuser:
        queryset = queryset.filter(family__memberships__user=request.user, family__status=Family.Status.ACTIVE)
    expense = queryset.distinct().first()
    if not expense:
        raise NotFound()

    if request.method == "DELETE":
        with transaction.atomic():
            locked = Expense.objects.select_for_update().filter(id=expense.id).first()
            if not locked:
                raise NotFound()
            extraction = getattr(locked, "extraction", None)
            locked.receipt_content = None
            locked.receipt_mime = ""
            locked.receipt_status = Expense.ReceiptStatus.NONE
            locked.updated_at = timezone.now()
            locked.save(update_fields=["receipt_content", "receipt_mime", "receipt_status", "updated_at"])
            if extraction:
                extraction.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    if not expense.receipt_content:
        raise NotFound()
    response = HttpResponse(bytes(expense.receipt_content), content_type=expense.receipt_mime or "image/jpeg")
    response["Content-Disposition"] = f'inline; filename="receipt-{expense.id}.jpg"'
    response["Cache-Control"] = "private, no-store"
    response["X-Content-Type-Options"] = "nosniff"
    return response
