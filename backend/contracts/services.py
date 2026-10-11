import calendar
from datetime import datetime, timedelta
import re

from django.utils import timezone
from django.utils.dateparse import parse_date

from documents.access import can_view_document
from documents.models import Document, DocumentLink
from family.models import FamilyEvent, Task

from .models import Contract, ContractReminder


PREFILL_KEYS = {
    "provider": "provider",
    "contract_provider": "provider",
    "contract.number": "contract_number",
    "contract_number": "contract_number",
    "customer_number": "customer_number",
    "contract.start_date": "start_date",
    "start_date": "start_date",
    "minimum_term_months": "minimum_term_months",
    "contract.end_date": "end_date",
    "end_date": "end_date",
    "cancellation_period": "cancellation_period",
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


def _period_components(value):
    match = re.fullmatch(
        r"\s*(\d+)\s*(tag|tage|tagen|day|days|woche|wochen|week|weeks|monat|monate|monaten|month|months|jahr|jahre|jahren|year|years)\s*",
        str(value or ""),
        re.IGNORECASE,
    )
    if not match:
        return None
    count = int(match.group(1))
    unit = match.group(2).casefold()
    if unit in {"tag", "tage", "tagen", "day", "days"}:
        return count, "days"
    if unit in {"woche", "wochen", "week", "weeks"}:
        return count, "weeks"
    if unit in {"monat", "monate", "monaten", "month", "months"}:
        return count, "months"
    return count, "years"


def subtract_period(value, period):
    parsed = _period_components(period)
    if not parsed:
        return None
    count, unit = parsed
    if unit == "days":
        return value - timedelta(days=count)
    if unit == "weeks":
        return value - timedelta(weeks=count)
    if unit == "months":
        return add_months(value, -count)
    return add_months(value, -(count * 12))


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
    if candidate_end and contract.cancellation_period:
        deadline = subtract_period(candidate_end, contract.cancellation_period)
        if deadline:
            results.append({
                "key": "cancellation_deadline",
                "date": deadline.isoformat(),
                "source_type": "derived",
                "based_on": ["end_date" if contract.end_date else "minimum_term_end", "cancellation_period"],
            })
    return results


def cancellation_deadline(contract):
    for item in derived_dates(contract):
        if item["key"] == "cancellation_deadline":
            return item["date"]
    return None


def _iso_date(value):
    text = str(value or "").strip()
    if not text:
        return text
    parsed = parse_date(text)
    if parsed:
        return parsed.isoformat()
    for pattern in ("%d.%m.%Y", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%y", "%d/%m/%y", "%d-%m-%y"):
        try:
            return datetime.strptime(text, pattern).date().isoformat()
        except ValueError:
            continue
    return text


def _mapped_value(field, value):
    if field in {"start_date", "end_date"}:
        return _iso_date(value)
    return value


def _suggestion(field, value, *, confidence, page, evidence_text, source_type="explicit", key=None):
    return {
        "field": field,
        "key": key or f"contract.{field}",
        "value": value,
        "confidence": float(confidence),
        "page": page,
        "evidence_text": str(evidence_text or "")[:2000],
        "source_type": source_type,
    }


def _page_rows(run):
    rows = []
    for extracted in run.extracted_fields.filter(key="text.page").order_by("page", "created_at"):
        value = extracted.value_json or {}
        text = value.get("text") if isinstance(value, dict) else ""
        if text:
            rows.append((extracted.page, str(text), float(extracted.confidence)))
    if not rows and run.normalized_text:
        rows.append((None, run.normalized_text, 0.75))
    return rows


def _line_match(rows, regex, *, field, transform=lambda value: value, source_type="explicit", confidence=0.9):
    compiled = re.compile(regex, re.IGNORECASE)
    for page, text, page_confidence in rows:
        for line in text.splitlines():
            match = compiled.search(line)
            if not match:
                continue
            raw = match.group("value").strip()
            value = transform(raw)
            if value in (None, ""):
                continue
            return _suggestion(
                field,
                value,
                confidence=min(confidence, page_confidence or confidence),
                page=page,
                evidence_text=line.strip(),
                source_type=source_type,
            )
    return None


def _minimum_term_months(raw):
    match = re.fullmatch(r"\s*(\d+)\s*(monat|monate|monaten|month|months|jahr|jahre|jahren|year|years)\s*", raw, re.IGNORECASE)
    if not match:
        return None
    count = int(match.group(1))
    return count * 12 if match.group(2).casefold() in {"jahr", "jahre", "jahren", "year", "years"} else count


def _amount_value(raw):
    value = re.sub(r"\s*(?:€|EUR)\s*$", "", raw, flags=re.IGNORECASE).replace(" ", "")
    if "," in value and "." in value:
        value = value.replace(".", "").replace(",", ".") if value.rfind(",") > value.rfind(".") else value.replace(",", "")
    else:
        value = value.replace(",", ".")
    return value


def _contract_text_suggestions(run):
    rows = _page_rows(run)
    candidates = [
        _line_match(rows, r"\b(?:anbieter|provider|vertragspartner)\b\s*(?:[:\-])?\s*(?P<value>.+)$", field="provider", confidence=0.88),
        _line_match(rows, r"\b(?:kundennummer|kunden[- ]?nr\.?|customer\s*(?:number|no\.?)?)\b\s*(?:[:#\-])?\s*(?P<value>[A-Z0-9][A-Z0-9./_-]{2,31})", field="customer_number", confidence=0.94),
        _line_match(rows, r"\b(?:mindestlaufzeit|laufzeit|minimum\s+term)\b\s*(?:[:\-])?\s*(?P<value>\d+\s*(?:monate?|monaten|months?|jahre?|jahren|years?))", field="minimum_term_months", transform=_minimum_term_months, source_type="derived", confidence=0.9),
        _line_match(rows, r"\b(?:kündigungsfrist|kuendigungsfrist|cancellation\s+period)\b\s*(?:[:\-])?\s*(?P<value>\d+\s*(?:tage?|tagen|days?|wochen?|weeks?|monate?|monaten|months?|jahre?|jahren|years?))", field="cancellation_period", confidence=0.94),
        _line_match(rows, r"\b(?:verlängerung|verlaengerung|renewal)\b\s*(?:[:\-])?\s*(?P<value>.+)$", field="renewal_rule", confidence=0.86),
        _line_match(rows, r"\b(?:betrag|preis|entgelt|kosten|amount|price)\b\s*(?:[:\-])?\s*(?P<value>\d{1,3}(?:[.\s]\d{3})*(?:,\d{2})|\d{1,6}[.,]\d{2})\s*(?:€|EUR)?", field="amount", transform=_amount_value, confidence=0.9),
    ]
    interval_terms = [
        ("monthly", ("monatlich", "pro monat", "monthly")),
        ("quarterly", ("vierteljährlich", "vierteljaehrlich", "quartalsweise", "quarterly")),
        ("half_year", ("halbjährlich", "halbjaehrlich", "half-yearly", "semiannual")),
        ("yearly", ("jährlich", "jaehrlich", "pro jahr", "yearly", "annual")),
        ("one_time", ("einmalig", "one-time", "one time")),
    ]
    for page, text, page_confidence in rows:
        lower = text.casefold()
        found = None
        for value, terms in interval_terms:
            term = next((term for term in terms if term in lower), None)
            if term:
                evidence = next((line.strip() for line in text.splitlines() if term in line.casefold()), term)
                found = _suggestion("billing_interval", value, confidence=min(0.84, page_confidence or 0.84), page=page, evidence_text=evidence, source_type="derived")
                break
        if found:
            candidates.append(found)
            break
    return [candidate for candidate in candidates if candidate]


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
    seen_fields = set()
    for extracted in run.extracted_fields.order_by("key", "page", "created_at"):
        field = PREFILL_KEYS.get(extracted.key)
        if not field or field in seen_fields:
            continue
        raw = extracted.value_json
        value = raw.get("value") if isinstance(raw, dict) and "value" in raw else raw
        suggestions.append(_suggestion(
            field,
            _mapped_value(field, value),
            key=extracted.key,
            confidence=extracted.confidence,
            page=extracted.page,
            evidence_text=extracted.evidence_text,
            source_type=extracted.source_type,
        ))
        seen_fields.add(field)
    for suggestion in _contract_text_suggestions(run):
        if suggestion["field"] not in seen_fields:
            suggestions.append(suggestion)
            seen_fields.add(suggestion["field"])
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

    starts_at = timezone.make_aware(datetime.combine(due_on, datetime.min.time())).replace(hour=9)
    if action == "task":
        return Task.objects.create(
            family=contract.family,
            title=f"Vertrag prüfen/kündigen: {contract.title}"[:180],
            due_at=starts_at,
            assignee=user,
            created_by=user,
            priority=Task.Priority.NORMAL,
            source=f"contract:{contract.id}",
        )
    if action == "event":
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
