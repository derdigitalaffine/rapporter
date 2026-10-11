from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation

from django.db import IntegrityError, transaction
from django.http import Http404
from django.utils import timezone
from django.utils.dateparse import parse_date
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from contracts.access import can_manage_contract
from contracts.models import Contract
from documents.access import can_manage_document, can_view_document
from documents.models import Document, DocumentLink
from expenses.models import Expense
from family.context_links import create_context_link
from family.models import FamilyEvent, Membership, ShoppingItem, ShoppingList, Task
from pets.models import PetProfile
from pets.permissions import pet_access

from .models import CorrespondenceReview
from .services import deterministic_summary, extract_suggestions, sanitize_review_data


def _document(user, document_id, *, manage=False):
    document = Document.objects.select_related("family", "owner_membership").filter(id=document_id, archived_at__isnull=True).first()
    if not document:
        raise Http404
    allowed = can_manage_document(user, document) if manage else can_view_document(user, document)
    if not allowed:
        raise Http404
    return document


def _review(document, user, *, create=False):
    review = CorrespondenceReview.objects.filter(document=document).first()
    if not review and create:
        review = CorrespondenceReview.objects.create(family=document.family, document=document, created_by=user, updated_by=user)
    return review


def _payload(document, review):
    run, suggestions = extract_suggestions(document)
    data = review.data if review else {}
    return {
        "document": {
            "id": str(document.id),
            "family": str(document.family_id),
            "title": document.title,
            "visibility": document.visibility,
            "processing_status": document.processing_status,
            "file_url": f"/api/documents/{document.id}/file/",
        },
        "processing_run": None if not run else {"id": str(run.id), "status": run.status, "extractor": run.extractor, "pipeline_version": run.pipeline_version},
        "review": {"data": data, "status": review.status if review else "open", "reviewed_at": review.reviewed_at.isoformat() if review and review.reviewed_at else None},
        "suggestions": suggestions,
        "summary": deterministic_summary(data, suggestions),
    }


def _deadline(data, payload):
    value = payload.get("due_on") or data.get("deadline")
    parsed = parse_date(str(value)) if value else None
    if value and not parsed:
        raise ValidationError({"due_on": "Ungültiges Datum."})
    return parsed


def _family_projection_allowed(document):
    return document.visibility == Document.Visibility.FAMILY


def _link_document(document, domain_type, object_id):
    return DocumentLink.objects.get_or_create(document=document, domain_type=domain_type, object_id=object_id, relationship="source")


@api_view(["GET", "PATCH"])
def correspondence_review(request, document_id):
    document = _document(request.user, document_id, manage=request.method == "PATCH")
    review = _review(document, request.user, create=request.method == "PATCH")
    if request.method == "PATCH":
        review.data = sanitize_review_data(request.data.get("data", request.data))
        if request.data.get("reviewed") is True:
            review.status = CorrespondenceReview.Status.REVIEWED
            review.reviewed_at = timezone.now()
        review.updated_by = request.user
        review.save(update_fields=["data", "status", "reviewed_at", "updated_by", "updated_at"])
    return Response(_payload(document, review))


@api_view(["POST"])
def correspondence_action(request, document_id):
    document = _document(request.user, document_id, manage=True)
    if request.data.get("confirmed") is not True:
        raise ValidationError({"confirmed": "Aktionen benötigen eine ausdrückliche Bestätigung."})
    review = _review(document, request.user, create=True)
    data = review.data or {}
    action = str(request.data.get("action") or "")
    if action == "store_only":
        review.status = CorrespondenceReview.Status.REVIEWED
        review.reviewed_at = timezone.now()
        review.updated_by = request.user
        review.save(update_fields=["status", "reviewed_at", "updated_by", "updated_at"])
        return Response({"kind": "stored", "id": str(review.id)})

    if action in {"task", "event", "shopping", "expense"} and not _family_projection_allowed(document):
        return Response({"code": "private_document_action", "detail": "Private oder selektiv geteilte Schreiben werden nicht in familienweite Zielobjekte kopiert."}, status=status.HTTP_409_CONFLICT)

    membership = Membership.objects.filter(family=document.family, user=request.user, family__status="active").first()
    if not membership:
        raise Http404
    title = str(request.data.get("title") or data.get("action_text") or data.get("subject") or document.title).strip()[:180]
    due_on = _deadline(data, request.data)

    if action == "task":
        starts_at = timezone.make_aware(datetime.combine(due_on, datetime.min.time())).replace(hour=9) if due_on else None
        created = Task.objects.create(family=document.family, title=title, notes=f"Aus Schreiben: {document.title}", due_at=starts_at, assignee=request.user, created_by=request.user, priority=Task.Priority.NORMAL, source=f"document:{document.id}")
        _link_document(document, DocumentLink.DomainType.TASK, created.id)
        return Response({"kind": "task", "id": str(created.id)}, status=status.HTTP_201_CREATED)

    if action == "event":
        if not due_on:
            raise ValidationError({"due_on": "Für einen Termin ist ein Datum erforderlich."})
        starts_at = timezone.make_aware(datetime.combine(due_on, datetime.min.time())).replace(hour=9)
        created = FamilyEvent.objects.create(family=document.family, type="correspondence", title=title[:200], starts_at=starts_at, ends_at=starts_at + timedelta(minutes=30), actionable=True, payload={"document_id": str(document.id), "source": "correspondence", "confirmed": True})
        _link_document(document, DocumentLink.DomainType.EVENT, created.id)
        return Response({"kind": "event", "id": str(created.id)}, status=status.HTTP_201_CREATED)

    if action == "shopping":
        shopping_list = ShoppingList.objects.filter(id=request.data.get("shopping_list"), family=document.family, archived=False).first()
        if not shopping_list:
            raise ValidationError({"shopping_list": "Gültige Einkaufsliste erforderlich."})
        created = ShoppingItem.objects.create(shopping_list=shopping_list, name=title[:160], note=f"Aus Schreiben {document.title}"[:240], added_by=request.user)
        create_context_link(user=request.user, family=document.family, source_type="document", source_id=document.id, context_type="shopping_item", context_id=created.id, relation_key="correspondence.action")
        return Response({"kind": "shopping_item", "id": str(created.id)}, status=status.HTTP_201_CREATED)

    if action == "expense":
        raw_amount = request.data.get("amount") or data.get("amount")
        try:
            amount = Decimal(str(raw_amount)) if raw_amount not in (None, "") else None
        except (InvalidOperation, TypeError, ValueError):
            raise ValidationError({"amount": "Ungültiger Betrag."}) from None
        if amount is None or amount <= 0:
            raise ValidationError({"amount": "Für eine Ausgabe ist ein positiver Betrag erforderlich."})
        try:
            with transaction.atomic():
                created = Expense.objects.create(family=document.family, title=title, merchant=str(data.get("sender") or "")[:180], total_amount=amount, paid_by=membership, created_by=request.user, receipt_document=document, source=Expense.Source.MANUAL, status=Expense.Status.POSTED)
                _link_document(document, DocumentLink.DomainType.EXPENSE, created.id)
        except IntegrityError:
            return Response({"code": "document_already_used", "detail": "Das Dokument ist bereits einer Ausgabe zugeordnet."}, status=status.HTTP_409_CONFLICT)
        return Response({"kind": "expense", "id": str(created.id)}, status=status.HTTP_201_CREATED)

    if action == "link":
        target_type = str(request.data.get("target_type") or "")
        target_id = request.data.get("target_id")
        if target_type == "contract":
            target = Contract.objects.filter(id=target_id, family=document.family, archived_at__isnull=True).first()
            if not target or not can_manage_contract(request.user, target):
                raise Http404
            _link_document(document, DocumentLink.DomainType.CONTRACT, target.id)
            return Response({"kind": "contract_link", "id": str(target.id)}, status=status.HTTP_201_CREATED)
        if target_type == "pet":
            target = PetProfile.objects.filter(id=target_id, family=document.family, active=True).first()
            if not target:
                raise Http404
            try:
                pet_access(request.user, document.family)
            except Exception:
                raise Http404
            _link_document(document, DocumentLink.DomainType.PET, target.id)
            return Response({"kind": "pet_link", "id": str(target.id)}, status=status.HTTP_201_CREATED)
        raise ValidationError({"target_type": "Unterstützt werden aktuell Vertrag und Haustier. Weitere kanonische Zieltypen werden über dieselbe Registry ergänzt."})

    raise ValidationError({"action": "Unbekannte Aktion."})
