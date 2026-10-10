import calendar
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from documents.access import can_view_document
from documents.models import Document, DocumentLink, ExtractedField
from family.models import FamilyEvent, Task

from .models import Contract, ContractReminder


PREFILL_KEYS = {
    "provider": "provider",
    "contract_provider": "provider",
    "contract_number": "contract_number",
    "customer_number": "customer_number",
    "start_date": "start_date",
    "minimum_term_months": "minimum_term_months",
    "end_date": "end_date",
    "cancellation_period_days": "cancellation_period_days",
    "renewal_rule": "renewal_rule",
    "amount": "amount",
    "billing_interval": "billing_interval",
}


def add_months(value, months):
    month_index = value.month - 1 + int(months)
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return value.replace(year=year, month=month, day=day)


def derived_dates(contract):
    results = []
    candidate_end = contract.end_date
    if candidate_end:
        results.append({
            "key": "contract_end",
            "date": candidate_end.isoformat(),
            "source_type": "explicit",
            "based_on": ["end_date"],
        })
    elif contract.start_date and contract.minimum_term_months is not None:
        candidate_end = add_months(contract.start_date, contract.minimum_term_months)
        results.append({
            "key": "minimum_term_end",
            "date": candidate_end.isoformat(),
            "source_type": "derived",
            "based_on": ["start_date", "minimum_term_months"],
        })
    if candidate_end and contract.cancellation_period_days is not None:
        deadline = candidate_end - timedelta(days=contract.cancellation_period_days)
        results.append({
            "key": "cancellation_deadline",
            "date": deadline.isoformat(),
            "source_type": "derived",
            "based_on": ["end_date" if contract.end_date else "minimum_term_end", "cancellation_period_days"],
        })
    return results


def cancellation_deadline(contract):
    for item in derived_dates(contract):
        if item["key"] == "cancellation_deadline":
            return item["date"]
    return None


def prefill_for_document(user, document):
    if not can_view_document(user, document):
        return None
    run = document.processing_runs.order_by("-created_at").first()
    if not run:
        return {
            "document": str(document.id),
            "processing_status": document.processing_status,
            "processing_run": None,
            "suggestions": [],
        }
    suggestions = []
    for extracted in run.extracted_fields.order_by("key", "page", "created_at"):
        field = PREFILL_KEYS.get(extracted.key)
        if not field:
            continue
        suggestions.append({
            "field": field,
            "key": extracted.key,
            "value": extracted.value_json,
            "confidence": float(extracted.confidence),
            "page": extracted.page,
            "evidence_text": extracted.evidence_text,
            "source_type": extracted.source_type,
        })
    return {
        "document": str(document.id),
        "processing_status": document.processing_status,
        "processing_run": {
            "id": str(run.id),
            "status": run.status,
            "extractor": run.extractor,
            "pipeline_version": run.pipeline_version,
        },
        "suggestions": suggestions,
    }


def attach_document(*, user, contract, document):
    if document.family_id != contract.family_id or document.archived_at is not None:
        raise ValueError("document_family_mismatch")
    if not can_view_document(user, document):
        raise PermissionError("document_not_visible")
    link, _ = DocumentLink.objects.get_or_create(
        document=document,
        domain_type=DocumentLink.DomainType.CONTRACT,
        object_id=contract.id,
        relationship="source",
    )
    return link


def detach_document(*, contract, document_id):
    return DocumentLink.objects.filter(
        document_id=document_id,
        domain_type=DocumentLink.DomainType.CONTRACT,
        object_id=contract.id,
    ).delete()[0]


def contract_documents(user, contract):
    document_ids = DocumentLink.objects.filter(
        domain_type=DocumentLink.DomainType.CONTRACT,
        object_id=contract.id,
    ).values_list("document_id", flat=True)
    documents = Document.objects.filter(id__in=document_ids, archived_at__isnull=True).order_by("-created_at")
    return [document for document in documents if can_view_document(user, document)]


def confirmed_follow_up(*, user, contract, action, due_on=None):
    if not due_on:
        due_on = cancellation_deadline(contract)
    if not due_on:
        raise ValueError("missing_due_date")
    if isinstance(due_on, str):
        from django.utils.dateparse import parse_date
        due_on = parse_date(due_on)
    if not due_on:
        raise ValueError("invalid_due_date")

    if action == "reminder":
        return ContractReminder.objects.create(
            contract=contract,
            due_on=due_on,
            label=f"Vertrag prüfen: {contract.title}"[:240],
            confirmed_at=timezone.now(),
            created_by=user,
        )

    # Tasks and calendar events are family-wide today. Do not leak private or
    # selectively shared contract titles into those canonical domains.
    if contract.visibility != Contract.Visibility.FAMILY:
        raise PermissionError("private_contract_action")

    if action == "task":
        return Task.objects.create(
            family=contract.family,
            title=f"Vertrag prüfen/kündigen: {contract.title}"[:180],
            due_at=timezone.make_aware(timezone.datetime.combine(due_on, timezone.datetime.min.time())).replace(hour=9),
            assignee=user,
            created_by=user,
            priority=Task.Priority.NORMAL,
            source=f"contract:{contract.id}",
        )
    if action == "event":
        starts_at = timezone.make_aware(timezone.datetime.combine(due_on, timezone.datetime.min.time())).replace(hour=9)
        return FamilyEvent.objects.create(
            family=contract.family,
            type="contract",
            title=f"Vertrag prüfen/kündigen: {contract.title}"[:200],
            starts_at=starts_at,
            ends_at=starts_at + timedelta(minutes=30),
            actionable=True,
            payload={"contract_id": str(contract.id), "confirmed": True},
        )
    raise ValueError("unknown_action")
