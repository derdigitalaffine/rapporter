from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.http import Http404
from django.utils import timezone
from django.utils.dateparse import parse_date
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from documents.models import Document
from family.models import Membership

from .access import active_membership, can_manage_contract, can_view_contract, visible_contracts
from .models import Contract, ContractAccess
from .serializers import contract_payload
from .services import attach_document, confirmed_follow_up, detach_document, prefill_for_document


def _date(value, field):
    if value in (None, ""):
        return None
    parsed = parse_date(str(value))
    if not parsed:
        raise ValidationError({field: "Ungültiges Datum."})
    return parsed


def _positive_int(value, field):
    if value in (None, ""):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValidationError({field: "Positive ganze Zahl erwartet."}) from exc
    if parsed < 0:
        raise ValidationError({field: "Wert darf nicht negativ sein."})
    return parsed


def _decimal(value, field):
    if value in (None, ""):
        return None
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValidationError({field: "Ungültiger Betrag."}) from exc
    if parsed < 0:
        raise ValidationError({field: "Betrag darf nicht negativ sein."})
    return parsed


def _prepare_access(family_id, value):
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValidationError({"access": "Eine Liste wird erwartet."})
    rows = []
    for raw in value:
        if not isinstance(raw, dict) or not raw.get("membership"):
            raise ValidationError({"access": "Jeder Zugriff benötigt eine Mitgliedschaft."})
        membership = Membership.objects.filter(id=raw["membership"], family_id=family_id).first()
        if not membership:
            raise ValidationError({"access": "Mitgliedschaft gehört nicht zu dieser Familie."})
        can_manage = bool(raw.get("can_manage", False))
        rows.append((membership, bool(raw.get("can_view", True)) or can_manage, can_manage))
    return rows


def _replace_access(contract, rows):
    contract.access_entries.all().delete()
    ContractAccess.objects.bulk_create([
        ContractAccess(contract=contract, membership=membership, can_view=can_view, can_manage=can_manage)
        for membership, can_view, can_manage in rows
        if membership.id != contract.owner_membership_id
    ])


def _contract_or_404(user, contract_id, require_manage=False):
    contract = Contract.objects.select_related("family", "owner_membership").prefetch_related(
        "access_entries", "reminders"
    ).filter(id=contract_id).first()
    if not contract:
        raise Http404
    allowed = can_manage_contract(user, contract) if require_manage else can_view_contract(user, contract)
    if not allowed or (contract.archived_at and not can_manage_contract(user, contract)):
        raise Http404
    return contract


def _apply_fields(contract, data):
    simple = {
        "category": 96,
        "provider": 180,
        "contract_number": 120,
        "customer_number": 120,
        "cancellation_period": 64,
        "renewal_rule": 240,
    }
    updates = []
    if "title" in data:
        title = str(data.get("title") or "").strip()
        if not title:
            raise ValidationError({"title": "Titel fehlt."})
        contract.title = title[:240]
        updates.append("title")
    for field, limit in simple.items():
        if field in data:
            setattr(contract, field, str(data.get(field) or "").strip()[:limit])
            updates.append(field)
    if "notes" in data:
        contract.notes = str(data.get("notes") or "")
        updates.append("notes")
    if "start_date" in data:
        contract.start_date = _date(data.get("start_date"), "start_date")
        updates.append("start_date")
    if "end_date" in data:
        contract.end_date = _date(data.get("end_date"), "end_date")
        updates.append("end_date")
    if "minimum_term_months" in data:
        contract.minimum_term_months = _positive_int(data.get("minimum_term_months"), "minimum_term_months")
        updates.append("minimum_term_months")
    if "amount" in data:
        contract.amount = _decimal(data.get("amount"), "amount")
        updates.append("amount")
    if "billing_interval" in data:
        value = str(data.get("billing_interval") or "")
        if value and value not in {choice for choice, _ in Contract.BillingInterval.choices}:
            raise ValidationError({"billing_interval": "Ungültiges Zahlungsintervall."})
        contract.billing_interval = value
        updates.append("billing_interval")
    if "status" in data:
        value = str(data.get("status") or "")
        if value not in {choice for choice, _ in Contract.Status.choices}:
            raise ValidationError({"status": "Ungültiger Status."})
        contract.status = value
        updates.append("status")
    if "visibility" in data:
        value = str(data.get("visibility") or "")
        if value not in {choice for choice, _ in Contract.Visibility.choices}:
            raise ValidationError({"visibility": "Ungültige Sichtbarkeit."})
        contract.visibility = value
        updates.append("visibility")
    return updates


@api_view(["GET", "POST"])
def contract_collection(request):
    if request.method == "GET":
        family_id = request.query_params.get("family")
        if not family_id or not active_membership(request.user, family_id):
            raise Http404
        contracts = visible_contracts(request.user, family_id).select_related("family", "owner_membership").prefetch_related("access_entries", "reminders")
        return Response([contract_payload(contract, request.user) for contract in contracts])

    family_id = request.data.get("family")
    membership = active_membership(request.user, family_id)
    if not membership:
        raise Http404
    title = str(request.data.get("title") or "").strip()
    if not title:
        raise ValidationError({"title": "Titel fehlt."})
    access_rows = _prepare_access(family_id, request.data.get("access"))
    contract = Contract(family_id=family_id, title=title[:240], owner_membership=membership, created_by=request.user)
    _apply_fields(contract, request.data)
    with transaction.atomic():
        contract.save()
        _replace_access(contract, access_rows)
    contract = _contract_or_404(request.user, contract.id, require_manage=True)
    return Response(contract_payload(contract, request.user), status=status.HTTP_201_CREATED)


@api_view(["GET", "PATCH", "DELETE"])
def contract_detail(request, contract_id):
    contract = _contract_or_404(request.user, contract_id, require_manage=request.method != "GET")
    if request.method == "GET":
        return Response(contract_payload(contract, request.user))
    if request.method == "DELETE":
        contract.archived_at = timezone.now()
        contract.save(update_fields=["archived_at", "updated_at"])
        return Response(status=status.HTTP_204_NO_CONTENT)
    access_rows = _prepare_access(contract.family_id, request.data.get("access")) if "access" in request.data else None
    updates = _apply_fields(contract, request.data)
    with transaction.atomic():
        if updates:
            contract.save(update_fields=[*updates, "updated_at"])
        if access_rows is not None:
            _replace_access(contract, access_rows)
    return Response(contract_payload(_contract_or_404(request.user, contract.id, require_manage=True), request.user))


@api_view(["GET"])
def contract_prefill(request):
    family_id = request.query_params.get("family")
    document_id = request.query_params.get("document")
    if not family_id or not document_id or not active_membership(request.user, family_id):
        raise Http404
    document = Document.objects.filter(id=document_id, family_id=family_id, archived_at__isnull=True).first()
    if not document:
        raise Http404
    payload = prefill_for_document(request.user, document)
    if payload is None:
        raise Http404
    return Response(payload)


@api_view(["POST"])
def contract_document_collection(request, contract_id):
    contract = _contract_or_404(request.user, contract_id, require_manage=True)
    document = Document.objects.filter(id=request.data.get("document"), archived_at__isnull=True).first()
    if not document:
        raise Http404
    try:
        attach_document(user=request.user, contract=contract, document=document)
    except (ValueError, PermissionError):
        raise Http404
    return Response(contract_payload(_contract_or_404(request.user, contract.id, require_manage=True), request.user), status=status.HTTP_201_CREATED)


@api_view(["DELETE"])
def contract_document_detail(request, contract_id, document_id):
    contract = _contract_or_404(request.user, contract_id, require_manage=True)
    if not detach_document(contract=contract, document_id=document_id):
        raise Http404
    return Response(status=status.HTTP_204_NO_CONTENT)


@api_view(["POST"])
def contract_action(request, contract_id):
    contract = _contract_or_404(request.user, contract_id, require_manage=True)
    if request.data.get("confirmed") is not True:
        raise ValidationError({"confirmed": "Folgeaktionen benötigen eine ausdrückliche Bestätigung."})
    action = str(request.data.get("action") or "")
    due_on = _date(request.data.get("due_on"), "due_on") if "due_on" in request.data else None
    try:
        created = confirmed_follow_up(user=request.user, contract=contract, action=action, due_on=due_on)
    except PermissionError:
        return Response(
            {"code": "private_contract_action", "detail": "Private oder selektiv geteilte Vertragsdaten werden nicht in familienweite Aufgaben oder Termine kopiert."},
            status=status.HTTP_409_CONFLICT,
        )
    except ValueError as exc:
        code = str(exc)
        return Response({"code": code, "detail": "Für diese Aktion fehlt ein gültiger Termin."}, status=status.HTTP_400_BAD_REQUEST)
    kind = "reminder" if action == "reminder" else action
    return Response({"kind": kind, "id": str(created.id)}, status=status.HTTP_201_CREATED)
