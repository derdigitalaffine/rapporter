from django.db import transaction
from django.http import FileResponse, HttpResponse
from django.utils import timezone
from rest_framework.decorators import api_view
from rest_framework.exceptions import NotFound
from rest_framework.response import Response
from rest_framework import status

from documents.storage import open_canonical, remove_canonical
from family.models import Family
from .models import Expense


@api_view(["GET", "DELETE"])
def receipt_file(request, expense_id):
    queryset = Expense.objects.select_related("receipt_document").filter(id=expense_id)
    if not request.user.is_superuser:
        queryset = queryset.filter(family__memberships__user=request.user, family__status=Family.Status.ACTIVE)
    expense = queryset.distinct().first()
    if not expense:
        raise NotFound()

    if request.method == "DELETE":
        with transaction.atomic():
            locked = Expense.objects.select_for_update().select_related("receipt_document").filter(id=expense.id).first()
            if not locked:
                raise NotFound()
            extraction = getattr(locked, "extraction", None)
            document = locked.receipt_document
            canonical_key = document.canonical_file if document else ""
            locked.receipt_content = None
            locked.receipt_document = None
            locked.receipt_mime = ""
            locked.receipt_status = Expense.ReceiptStatus.NONE
            locked.updated_at = timezone.now()
            locked.save(
                update_fields=["receipt_content", "receipt_document", "receipt_mime", "receipt_status", "updated_at"]
            )
            if extraction:
                extraction.delete()
            if document:
                document.delete()
                transaction.on_commit(lambda key=canonical_key: remove_canonical(key))
        return Response(status=status.HTTP_204_NO_CONTENT)

    if expense.receipt_document_id:
        try:
            handle = open_canonical(expense.receipt_document.canonical_file)
        except (FileNotFoundError, OSError):
            raise NotFound()
        extension = "pdf" if expense.receipt_document.mime_type == "application/pdf" else "webp"
        response = FileResponse(
            handle,
            content_type=expense.receipt_document.mime_type,
            as_attachment=False,
            filename=f"receipt-{expense.id}.{extension}",
        )
        response["Content-Length"] = str(expense.receipt_document.size)
    else:
        if not expense.receipt_content:
            raise NotFound()
        response = HttpResponse(bytes(expense.receipt_content), content_type=expense.receipt_mime or "image/jpeg")
        response["Content-Disposition"] = f'inline; filename="receipt-{expense.id}.jpg"'

    response["Cache-Control"] = "private, no-store"
    response["X-Content-Type-Options"] = "nosniff"
    return response
