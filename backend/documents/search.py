import re
from uuid import UUID

from django.contrib.postgres.search import SearchQuery, SearchRank, SearchVector
from django.db.models import F, Max, Q
from django.utils.dateparse import parse_date
from rest_framework.exceptions import ValidationError

from .access import can_manage_document, visible_documents
from .models import Document, DocumentSearchIndex

SEARCHABLE_FIELD_KEYS = {
    "reference",
    "reference_number",
    "case_number",
    "aktenzeichen",
    "document.reference",
    "letter.reference",
    "contract.number",
    "contract.provider",
    "contract.start_date",
    "contract.end_date",
    "receipt.merchant",
    "receipt.total",
    "receipt.date",
    "iban",
    "bank.iban",
}
MAX_QUERY_LENGTH = 200
MAX_RESULTS = 100
DEFAULT_RESULTS = 40


def _value_text(value):
    if value is None:
        return ""
    if isinstance(value, dict):
        if "value" in value:
            return _value_text(value.get("value"))
        return " ".join(_value_text(item) for item in value.values())
    if isinstance(value, (list, tuple)):
        return " ".join(_value_text(item) for item in value)
    return str(value)


def build_search_content(document, *, run=None):
    parts = [document.title, document.correspondent, document.kind]
    if run is None:
        run = (
            document.processing_runs.exclude(normalized_text="")
            .order_by("-processed_at", "-created_at")
            .first()
        )
    if run:
        parts.append(run.normalized_text)
        values = run.extracted_fields.filter(key__in=SEARCHABLE_FIELD_KEYS).values_list("value_json", flat=True)
        parts.extend(_value_text(value)[:2000] for value in values)
    return "\n".join(str(part).strip() for part in parts if str(part or "").strip())


def refresh_document_search_index(document, *, run=None):
    if not document.library_visible:
        DocumentSearchIndex.objects.filter(document=document).delete()
        return None
    content = build_search_content(document, run=run)
    index, _ = DocumentSearchIndex.objects.update_or_create(document=document, defaults={"content": content})
    DocumentSearchIndex.objects.filter(pk=index.pk).update(search_vector=SearchVector("content", config="simple"))
    index.refresh_from_db(fields=["search_vector", "updated_at"])
    return index


def refresh_document_search_index_by_id(document_id):
    document = Document.objects.filter(pk=document_id).first()
    if document:
        refresh_document_search_index(document)


def ensure_visible_search_indexes(user, family_id):
    """Refresh only visible rows whose derived material is missing or stale.

    ACL filtering happens before this maintenance query. Search material therefore
    never becomes an alternate way to enumerate private documents.
    """
    stale = (
        visible_documents(user, family_id)
        .annotate(latest_run_updated=Max("processing_runs__updated_at"))
        .filter(
            Q(search_index__isnull=True)
            | Q(search_index__updated_at__lt=F("updated_at"))
            | Q(search_index__updated_at__lt=F("latest_run_updated"))
        )
        .only("id", "title", "correspondent", "kind", "library_visible", "updated_at")
        .order_by("id")
    )
    for document in stale.iterator(chunk_size=100):
        refresh_document_search_index(document)


def _date_filter(params, key):
    value = params.get(key)
    if not value:
        return None
    parsed = parse_date(str(value))
    if not parsed:
        raise ValidationError({key: "Ungültiges Datum."})
    return parsed


def _bool_filter(params, key):
    value = params.get(key)
    if value in (None, ""):
        return None
    normalized = str(value).lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValidationError({key: "Boolean-Wert erwartet."})


def _membership_id(params):
    value = params.get("person")
    if not value:
        return None
    try:
        return UUID(str(value))
    except (TypeError, ValueError, AttributeError):
        raise ValidationError({"person": "Ungültige Mitgliedschaft."}) from None


def _limit(params):
    raw = params.get("limit", DEFAULT_RESULTS)
    try:
        value = int(raw)
    except (TypeError, ValueError):
        raise ValidationError({"limit": "Ganzzahl erwartet."}) from None
    if not 1 <= value <= MAX_RESULTS:
        raise ValidationError({"limit": f"limit muss zwischen 1 und {MAX_RESULTS} liegen."})
    return value


def search_documents(user, family_id, params):
    """Search only inside the canonical ACL-filtered Document queryset."""
    query_text = str(params.get("q") or "").strip()
    if len(query_text) > MAX_QUERY_LENGTH:
        raise ValidationError({"q": f"Maximal {MAX_QUERY_LENGTH} Zeichen."})

    ensure_visible_search_indexes(user, family_id)
    queryset = (
        visible_documents(user, family_id)
        .select_related("owner_membership", "search_index")
        .prefetch_related("access_entries", "domain_links")
    )

    kind = str(params.get("kind") or "").strip()
    if kind:
        queryset = queryset.filter(kind=kind[:64])
    visibility = str(params.get("visibility") or "").strip()
    if visibility:
        allowed = {choice for choice, _ in Document.Visibility.choices}
        if visibility not in allowed:
            raise ValidationError({"visibility": "Ungültige Sichtbarkeit."})
        queryset = queryset.filter(visibility=visibility)
    pinned = _bool_filter(params, "pinned")
    if pinned is not None:
        queryset = queryset.filter(pinned=pinned)
    person = _membership_id(params)
    if person:
        queryset = queryset.filter(Q(owner_membership_id=person) | Q(access_entries__membership_id=person)).distinct()
    date_from = _date_filter(params, "date_from")
    if date_from:
        queryset = queryset.filter(document_date__gte=date_from)
    date_to = _date_filter(params, "date_to")
    if date_to:
        queryset = queryset.filter(document_date__lte=date_to)
    correspondent = str(params.get("correspondent") or "").strip()
    if correspondent:
        queryset = queryset.filter(correspondent__icontains=correspondent[:180])

    if query_text:
        query = SearchQuery(query_text, config="simple", search_type="websearch")
        queryset = (
            queryset.filter(search_index__search_vector=query)
            .annotate(search_rank=SearchRank(F("search_index__search_vector"), query))
            .order_by("-search_rank", "-document_date", "-created_at")
        )
    else:
        queryset = queryset.order_by("-document_date", "-created_at")
    return list(queryset[: _limit(params)]), query_text


def _query_tokens(query_text):
    return [token.casefold() for token in re.findall(r"[\w@.+-]{2,}", query_text, re.UNICODE)[:8]]


def safe_snippet(content, query_text, *, radius=110):
    text = " ".join(str(content or "").split())
    if not text or not query_text:
        return ""
    folded = text.casefold()
    positions = [folded.find(token) for token in _query_tokens(query_text)]
    positions = [position for position in positions if position >= 0]
    if not positions:
        return text[: radius * 2] + ("…" if len(text) > radius * 2 else "")
    center = min(positions)
    start = max(0, center - radius)
    end = min(len(text), center + radius)
    prefix = "…" if start else ""
    suffix = "…" if end < len(text) else ""
    return f"{prefix}{text[start:end]}{suffix}"


def search_result_payload(document, user, query_text):
    index = getattr(document, "search_index", None)
    return {
        "id": str(document.id),
        "family": str(document.family_id),
        "title": document.title,
        "kind": document.kind,
        "document_date": document.document_date.isoformat() if document.document_date else None,
        "correspondent": document.correspondent,
        "visibility": document.visibility,
        "owner_membership": str(document.owner_membership_id),
        "processing_status": document.processing_status,
        "pinned": document.pinned,
        "snippet": safe_snippet(index.content if index else "", query_text),
        "file_url": f"/api/documents/{document.id}/file/",
        "can_manage": can_manage_document(user, document),
    }
