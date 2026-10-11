import re
from collections.abc import Iterable
from uuid import UUID

from django.contrib.postgres.search import SearchQuery, SearchRank, SearchVector
from django.db import transaction
from django.db.models import F, Q

from family.models import Family, Membership

from .access import visible_documents
from .models import Document, DocumentProcessingRun, DocumentSearchIndex

SEARCH_CONFIG = "simple"
SEARCHABLE_EXTRACTED_FIELD_KEYS = frozenset(
    {
        "reference_number",
        "document_number",
        "invoice_number",
        "contract_number",
        "customer_number",
        "policy_number",
        "claim_number",
        "order_number",
        "tracking_number",
        "merchant",
        "provider",
        "issuer",
        "recipient",
        "subject",
    }
)
SEARCHABLE_RUN_STATUSES = (
    DocumentProcessingRun.Status.REVIEW,
    DocumentProcessingRun.Status.READY,
)


def _flatten_value(value):
    if value is None or isinstance(value, bool):
        return []
    if isinstance(value, (str, int, float)):
        return [str(value)]
    if isinstance(value, dict):
        values = []
        for nested in value.values():
            values.extend(_flatten_value(nested))
        return values
    if isinstance(value, Iterable):
        values = []
        for nested in value:
            values.extend(_flatten_value(nested))
        return values
    return []


def _normalize_search_text(parts):
    return "\n".join(
        cleaned
        for part in parts
        if (cleaned := re.sub(r"\s+", " ", str(part or "")).strip())
    )


def latest_searchable_run(document):
    return (
        document.processing_runs.filter(status__in=SEARCHABLE_RUN_STATUSES)
        .order_by("-processed_at", "-created_at")
        .first()
    )


def build_document_search_text(document, processing_run=None):
    run = processing_run or latest_searchable_run(document)
    parts = [document.title, document.correspondent, document.kind]
    if run:
        parts.append(run.normalized_text)
        fields = run.extracted_fields.filter(key__in=SEARCHABLE_EXTRACTED_FIELD_KEYS).only("value_json")
        for field in fields:
            parts.extend(_flatten_value(field.value_json))
    return _normalize_search_text(parts), run


@transaction.atomic
def rebuild_document_search_index(document_id, *, processing_run=None):
    document = Document.objects.select_for_update().get(pk=document_id)
    if processing_run is not None and processing_run.document_id != document.id:
        raise ValueError("processing run does not belong to document")
    search_text, run = build_document_search_text(document, processing_run)
    index, _ = DocumentSearchIndex.objects.update_or_create(
        document=document,
        defaults={
            "search_text": search_text,
            "indexed_processing_run": run,
        },
    )
    DocumentSearchIndex.objects.filter(pk=index.pk).update(
        search_vector=SearchVector("search_text", config=SEARCH_CONFIG)
    )
    return DocumentSearchIndex.objects.get(pk=index.pk)


def _snippet(text, query, *, radius=110, maximum=260):
    text = re.sub(r"\s+", " ", text or "").strip()
    if not text:
        return ""
    terms = [term.casefold() for term in re.findall(r"[\w-]+", query or "", flags=re.UNICODE) if len(term) > 1]
    haystack = text.casefold()
    positions = [position for term in terms if (position := haystack.find(term)) >= 0]
    if not positions:
        return text[:maximum] + ("…" if len(text) > maximum else "")
    position = min(positions)
    start = max(0, position - radius)
    end = min(len(text), position + radius + maximum // 3)
    prefix = "…" if start else ""
    suffix = "…" if end < len(text) else ""
    return f"{prefix}{text[start:end].strip()}{suffix}"


def document_search_queryset(user, family_id, *, query="", filters=None):
    filters = filters or {}
    queryset = visible_documents(user, family_id).select_related("owner_membership", "search_index")

    kind = filters.get("kind")
    if kind:
        queryset = queryset.filter(kind=kind)

    visibility = filters.get("visibility")
    if visibility == "shared":
        queryset = queryset.filter(visibility__in=[Document.Visibility.FAMILY, Document.Visibility.SELECTED])
    elif visibility:
        queryset = queryset.filter(visibility=visibility)

    person = filters.get("person")
    if person:
        queryset = queryset.filter(
            Q(owner_membership_id=person)
            | Q(access_entries__membership_id=person, access_entries__can_view=True)
        ).distinct()

    correspondent = filters.get("correspondent")
    if correspondent:
        queryset = queryset.filter(correspondent__icontains=correspondent)

    if filters.get("date_from"):
        queryset = queryset.filter(document_date__gte=filters["date_from"])
    if filters.get("date_to"):
        queryset = queryset.filter(document_date__lte=filters["date_to"])
    if filters.get("pinned") is not None:
        queryset = queryset.filter(pinned=filters["pinned"])

    query = (query or "").strip()
    if query:
        search_query = SearchQuery(query, search_type="websearch", config=SEARCH_CONFIG)
        queryset = queryset.filter(search_index__search_vector=search_query).annotate(
            search_rank=SearchRank(F("search_index__search_vector"), search_query)
        ).order_by("-search_rank", "-document_date", "-created_at")
    return queryset


def validate_person_filter(family_id, person_id):
    if not person_id:
        return True
    try:
        person_id = UUID(str(person_id))
    except (TypeError, ValueError, AttributeError):
        return False
    return Membership.objects.filter(
        id=person_id,
        family_id=family_id,
        family__status=Family.Status.ACTIVE,
    ).exists()


def search_result_payload(document, query=""):
    index = getattr(document, "search_index", None)
    return {
        "id": str(document.id),
        "title": document.title,
        "kind": document.kind,
        "document_date": document.document_date.isoformat() if document.document_date else None,
        "correspondent": document.correspondent,
        "visibility": document.visibility,
        "pinned": document.pinned,
        "processing_status": document.processing_status,
        "file_url": f"/api/documents/{document.id}/file/",
        "snippet": _snippet(index.search_text if index else "", query),
    }
