from datetime import datetime
from decimal import Decimal, InvalidOperation
import re

from django.utils.dateparse import parse_date


FIELD_KEYS = {
    "sender": {"sender", "document.sender", "letter.sender", "correspondent"},
    "recipient": {"recipient", "document.recipient", "letter.recipient"},
    "document_date": {"date", "document.date", "letter.date", "document_date"},
    "subject": {"subject", "document.subject", "letter.subject"},
    "reference_number": {"reference", "reference_number", "case_number", "document.reference", "aktenzeichen"},
    "amount": {"amount", "total", "document.amount", "letter.amount"},
    "iban": {"iban", "bank.iban"},
    "deadline": {"deadline", "due_date", "document.deadline", "letter.deadline"},
    "contact": {"contact", "email", "phone", "document.contact"},
}

ALLOWED_FIELDS = tuple(FIELD_KEYS) + ("action_text", "action_kind")
ACTION_WORDS = {
    "submit": ("einreichen", "vorlegen", "nachreichen", "submit"),
    "pay": ("bezahlen", "zahlen", "überweisen", "ueberweisen", "payment", "pay "),
    "return": ("zurücksenden", "zuruecksenden", "zurückschicken", "return"),
    "sign": ("unterschreiben", "unterschrift", "sign"),
    "reply": ("antworten", "rückmeldung", "rueckmeldung", "reply", "respond"),
    "appeal": ("widerspruch", "einspruch", "appeal", "objection"),
    "appointment": ("termin", "appointment"),
}


def _scalar(value):
    if isinstance(value, dict) and "value" in value:
        return value["value"]
    return value


def _iso_date(value):
    text = str(value or "").strip()
    if not text:
        return ""
    parsed = parse_date(text)
    if parsed:
        return parsed.isoformat()
    for pattern in ("%d.%m.%Y", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%y", "%d/%m/%y"):
        try:
            return datetime.strptime(text, pattern).date().isoformat()
        except ValueError:
            pass
    return text


def _money(value):
    text = str(value or "").strip()
    match = re.search(r"-?\d{1,3}(?:[.\s]\d{3})*(?:,\d{2})|-?\d+(?:[.,]\d{2})", text)
    if not match:
        return text
    number = match.group(0).replace(" ", "")
    if "," in number and "." in number:
        number = number.replace(".", "").replace(",", ".") if number.rfind(",") > number.rfind(".") else number.replace(",", "")
    else:
        number = number.replace(",", ".")
    return number


def _iban(value):
    compact = re.sub(r"\s+", "", str(value or "")).upper()
    return compact if re.fullmatch(r"[A-Z]{2}\d{2}[A-Z0-9]{11,30}", compact) else str(value or "").strip()


def _normalize(field, value):
    if field in {"document_date", "deadline"}:
        return _iso_date(value)
    if field == "amount":
        return _money(value)
    if field == "iban":
        return _iban(value)
    return str(value or "").strip()


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


def _suggest(field, value, *, confidence, page=None, evidence="", source_type="explicit", uncertain=False, key=None):
    return {
        "field": field,
        "key": key or field,
        "value": _normalize(field, value),
        "confidence": round(float(confidence), 4),
        "page": page,
        "evidence_text": str(evidence or "").strip()[:2000],
        "source_type": source_type,
        "uncertain": bool(uncertain),
    }


def _label(rows, field, labels, pattern=r".+", confidence=0.9, transform=None):
    label_expr = "|".join(re.escape(label) for label in labels)
    regex = re.compile(rf"\b(?:{label_expr})\b\s*(?:[:#\-])?\s*(?P<value>{pattern})\s*$", re.IGNORECASE)
    for page, text, page_confidence in rows:
        for line in text.splitlines():
            match = regex.search(line.strip())
            if match:
                value = match.group("value").strip()
                if transform:
                    value = transform(value)
                if value:
                    return _suggest(field, value, confidence=min(confidence, page_confidence or confidence), page=page, evidence=line)
    return None


def _deadline(rows):
    explicit = _label(rows, "deadline", ("frist", "deadline", "fällig am", "faellig am"), r"(?:\d{1,2}[./-]\d{1,2}[./-]\d{2,4}|\d{4}-\d{2}-\d{2}).*", 0.94, lambda value: re.split(r"\s", value, 1)[0])
    if explicit:
        return explicit
    regex = re.compile(r"\b(?:bis(?:\s+spätestens|\s+spaetestens|\s+zum)?|spätestens\s+am|spaetestens\s+am)\s+(?P<value>\d{1,2}[./-]\d{1,2}[./-]\d{2,4}|\d{4}-\d{2}-\d{2})", re.IGNORECASE)
    for page, text, page_confidence in rows:
        for line in text.splitlines():
            match = regex.search(line)
            if match:
                return _suggest("deadline", match.group("value"), confidence=min(0.9, page_confidence or 0.9), page=page, evidence=line)
    return None


def _contact(rows):
    for page, text, page_confidence in rows:
        email = re.search(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", text, re.IGNORECASE)
        phone = re.search(r"(?:\+\d{1,3}[\s/-]?)?(?:\(?\d{2,5}\)?[\s/-]?){2,}\d{2,}", text)
        if email or phone:
            value = email.group(0) if email else phone.group(0).strip()
            evidence = next((line.strip() for line in text.splitlines() if value in line), value)
            return _suggest("contact", value, confidence=min(0.92, page_confidence or 0.92), page=page, evidence=evidence)
    return None


def _iban_suggestion(rows):
    regex = re.compile(r"\b[A-Z]{2}\d{2}(?:\s?[A-Z0-9]){11,30}\b", re.IGNORECASE)
    for page, text, page_confidence in rows:
        match = regex.search(text)
        if match:
            evidence = next((line.strip() for line in text.splitlines() if match.group(0) in line), match.group(0))
            return _suggest("iban", match.group(0), confidence=min(0.96, page_confidence or 0.96), page=page, evidence=evidence)
    return None


def _action(rows):
    for page, text, page_confidence in rows:
        for line in text.splitlines():
            cleaned = line.strip()
            lower = cleaned.casefold()
            if len(cleaned) < 8:
                continue
            for kind, words in ACTION_WORDS.items():
                if any(word in lower for word in words):
                    return _suggest("action_text", cleaned, confidence=min(0.78, page_confidence or 0.78), page=page, evidence=cleaned, source_type="suggestion", uncertain=True, key=kind)
            if re.search(r"\bbis(?:\s+spätestens|\s+spaetestens|\s+zum)?\s+\d{1,2}[./-]\d{1,2}", lower):
                return _suggest("action_text", cleaned, confidence=min(0.7, page_confidence or 0.7), page=page, evidence=cleaned, source_type="suggestion", uncertain=True, key="deadline")
    return None


def extract_suggestions(document):
    run = document.processing_runs.order_by("-created_at").first()
    if not run:
        return None, []
    suggestions = []
    seen = set()
    reverse = {key: field for field, keys in FIELD_KEYS.items() for key in keys}
    for extracted in run.extracted_fields.exclude(key="text.page").order_by("key", "page", "created_at"):
        field = reverse.get(extracted.key)
        if not field or field in seen:
            continue
        value = _scalar(extracted.value_json)
        suggestions.append(_suggest(field, value, confidence=extracted.confidence, page=extracted.page, evidence=extracted.evidence_text, source_type=extracted.source_type, key=extracted.key))
        seen.add(field)
    rows = _page_rows(run)
    candidates = [
        _label(rows, "sender", ("absender", "von", "sender"), r".+", 0.9),
        _label(rows, "recipient", ("empfänger", "empfaenger", "an", "recipient"), r".+", 0.88),
        _label(rows, "document_date", ("datum", "schreiben vom", "date"), r"(?:\d{1,2}[./-]\d{1,2}[./-]\d{2,4}|\d{4}-\d{2}-\d{2})", 0.92),
        _label(rows, "subject", ("betreff", "subject"), r".+", 0.92),
        _label(rows, "reference_number", ("aktenzeichen", "geschäftszeichen", "geschaeftszeichen", "versicherungsnummer", "kundennummer", "reference"), r"[A-Z0-9][A-Z0-9 ./_\-]{2,80}", 0.93),
        _label(rows, "amount", ("betrag", "forderung", "gesamtbetrag", "amount"), r"\d[\d.\s]*(?:,\d{2}|\.\d{2})\s*(?:€|EUR)?", 0.9),
        _iban_suggestion(rows),
        _deadline(rows),
        _contact(rows),
        _action(rows),
    ]
    for candidate in candidates:
        if candidate and candidate["field"] not in seen:
            suggestions.append(candidate)
            seen.add(candidate["field"])
    return run, suggestions


def sanitize_review_data(data):
    if not isinstance(data, dict):
        return {}
    cleaned = {}
    for field in ALLOWED_FIELDS:
        value = data.get(field)
        if value in (None, ""):
            continue
        normalized = _normalize(field, value)
        cleaned[field] = str(normalized)[:2000]
    return cleaned


def deterministic_summary(data, suggestions):
    merged = dict(data or {})
    for suggestion in suggestions:
        if suggestion["field"] in merged or suggestion["uncertain"] or suggestion["confidence"] < 0.85:
            continue
        merged[suggestion["field"]] = suggestion["value"]
    parts = []
    if merged.get("sender"):
        parts.append(f"Schreiben von {merged['sender']}.")
    if merged.get("subject"):
        parts.append(f"Betreff: {merged['subject']}.")
    if merged.get("reference_number"):
        parts.append(f"Akten-/Referenzzeichen: {merged['reference_number']}.")
    if merged.get("amount"):
        parts.append(f"Genannter Betrag: {merged['amount']}.")
    if merged.get("deadline"):
        parts.append(f"Genannte Frist: {merged['deadline']}.")
    if data.get("action_text"):
        parts.append(f"Bestätigte Handlung: {data['action_text']}.")
    return " ".join(parts)
