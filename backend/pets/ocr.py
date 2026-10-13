import hashlib
import io
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation

from django.utils import timezone
from pypdf import PdfReader

from documents.extraction import ExtractionResult
from documents.intelligence import extract_invoice
from documents.legacy_image import canonicalize_legacy_image, extract_legacy_image_text

from .models import PetDocument

MAX_DOCUMENT_BYTES = 30 * 1024 * 1024
MAX_DOCUMENT_TEXT = 60000
MAX_PDF_PAGES = 25
DATE_RE = re.compile(r"\b(\d{1,2})[./-](\d{1,2})[./-](\d{2,4})\b")
ISO_DATE_RE = re.compile(r"\b(20\d{2})-(\d{1,2})-(\d{1,2})\b")
WEIGHT_RE = re.compile(r"\b(\d{1,3}(?:[.,]\d{1,3})?)\s*(kg|kilogramm|kilograms?)\b", re.I)
CHIP_RE = re.compile(r"\b(?:chip|mikrochip|microchip|transponder)[^\d]{0,20}(\d{12,18})\b", re.I)
DOSE_RE = re.compile(r"\b(\d+(?:[.,]\d+)?)\s*(mg|ml|µg|ug|g|tabletten?|tabs?)\b", re.I)
FREQUENCY_RE = re.compile(r"\b(?:\d+\s*[x×]\s*(?:täglich|taeglich|daily|pro tag|per day)|alle\s+\d+\s*(?:stunden|hours?)|every\s+\d+\s*hours?)\b", re.I)
TIME_RE = re.compile(r"\b(?:[01]?\d|2[0-3]):[0-5]\d\b")


def _parse_date(match):
    if not match:
        return None
    groups = match.groups()
    try:
        if len(groups) == 3 and len(groups[0]) == 4:
            year, month, day = map(int, groups)
        else:
            day, month, year = groups
            year = int(year)
            if year < 100:
                year += 2000
            month = int(month)
            day = int(day)
        return datetime(year, month, day).date().isoformat()
    except (TypeError, ValueError):
        return None


def _dates(text):
    found = []
    for expression in (ISO_DATE_RE, DATE_RE):
        for match in expression.finditer(text or ""):
            value = _parse_date(match)
            if value and value not in found:
                found.append(value)
    return found


def _line_with_keywords(lines, keywords):
    keys = tuple(k.casefold() for k in keywords)
    for line in lines:
        lower = line.casefold()
        if any(key in lower for key in keys):
            return line
    return ""


def _decimal_text(value):
    try:
        normalized = str(value or "").replace("EUR", "").replace("€", "").replace(" ", "").strip()
        if "," in normalized and "." in normalized:
            decimal_separator = "," if normalized.rfind(",") > normalized.rfind(".") else "."
            thousands_separator = "." if decimal_separator == "," else ","
            normalized = normalized.replace(thousands_separator, "").replace(decimal_separator, ".")
        else:
            normalized = normalized.replace(",", ".")
        return str(Decimal(normalized).quantize(Decimal("0.01")))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _generic_invoice_suggestions(text):
    """Consume shared labelled invoice fields without depending on Expense code."""
    result = ExtractionResult(text=text or "", extractor="pet-legacy-adapter")
    fields = {field["key"]: field for field in extract_invoice(result)}
    data = {}
    confidence = {}
    total_field = fields.get("amount.total")
    if total_field:
        total = _decimal_text((total_field.get("value_json") or {}).get("value"))
        if total is not None:
            data["total"] = total
            data["currency"] = "EUR"
            confidence["total"] = float(total_field.get("confidence") or 0)
            confidence["currency"] = 0.96 if ("€" in (text or "") or "eur" in (text or "").casefold()) else 0.55
    date_field = fields.get("document.date")
    if date_field:
        raw_date = str((date_field.get("value_json") or {}).get("value") or "")
        match = ISO_DATE_RE.search(raw_date) or DATE_RE.search(raw_date)
        value = _parse_date(match)
        if value:
            data["occurred_at"] = value
            confidence["occurred_at"] = float(date_field.get("confidence") or 0)
    return data, confidence


def extract_pet_fields(text, filename=""):
    text = (text or "")[:MAX_DOCUMENT_TEXT]
    lines = [re.sub(r"\s+", " ", line).strip() for line in text.splitlines() if line.strip()]
    lower = text.casefold()
    data = {}
    confidence = {}
    kind = PetDocument.Kind.OTHER

    invoice_fields, invoice_confidence = _generic_invoice_suggestions(text)
    if any(key in lower for key in ("rechnung", "invoice", "gesamt", "total", "zu zahlen")) and invoice_fields.get("total") is not None:
        kind = PetDocument.Kind.INVOICE
        data.update(invoice_fields)
        confidence.update(invoice_confidence)

    vaccine_line = _line_with_keywords(lines, ("impfung", "impfstoff", "vaccin", "rabies", "tollwut"))
    if vaccine_line:
        kind = PetDocument.Kind.VACCINATION
        data["vaccination"] = vaccine_line[:240]
        confidence["vaccination"] = 0.8

    prescription_line = _line_with_keywords(lines, ("rezept", "medikament", "medication", "dosierung", "dose", "tablette"))
    dose = DOSE_RE.search(text)
    if prescription_line or dose:
        if kind == PetDocument.Kind.OTHER:
            kind = PetDocument.Kind.PRESCRIPTION
        if prescription_line:
            data["medication_text"] = prescription_line[:240]
            confidence["medication_text"] = 0.72
        if dose:
            data["documented_dose"] = f"{dose.group(1).replace(',', '.')} {dose.group(2)}"
            confidence["documented_dose"] = 0.82
        frequency = FREQUENCY_RE.search(text)
        if frequency:
            data["documented_frequency"] = frequency.group(0)
            confidence["documented_frequency"] = 0.8
        times = list(dict.fromkeys(TIME_RE.findall(text)))[:8]
        if times:
            data["documented_times"] = times
            confidence["documented_times"] = 0.78

    chip = CHIP_RE.search(text)
    if chip:
        if kind == PetDocument.Kind.OTHER:
            kind = PetDocument.Kind.REGISTRATION
        data["microchip_id"] = chip.group(1)
        confidence["microchip_id"] = 0.88

    weight = WEIGHT_RE.search(text)
    if weight:
        data["weight_kg"] = weight.group(1).replace(",", ".")
        confidence["weight_kg"] = 0.82

    due_keys = ("nächste", "naechste", "fällig", "faellig", "next due", "due date", "gültig bis", "gueltig bis", "valid until")
    for line in lines:
        if not any(key in line.casefold() for key in due_keys):
            continue
        match = ISO_DATE_RE.search(line) or DATE_RE.search(line)
        value = _parse_date(match)
        if value:
            data["next_due_at"] = value
            confidence["next_due_at"] = 0.9
            break

    dates = _dates(text)
    if dates and not data.get("occurred_at"):
        data["occurred_at"] = dates[0]
        confidence["occurred_at"] = 0.66

    provider_line = _line_with_keywords(lines[:20], ("tierarzt", "praxis", "klinik", "veterinary", "veterinarian", "vet "))
    if provider_line and not data.get("provider_name"):
        data["provider_name"] = provider_line[:180]
        confidence["provider_name"] = 0.65

    if kind == PetDocument.Kind.OTHER and any(key in lower for key in ("labor", "laboratory", "befund")):
        kind = PetDocument.Kind.LAB
    if kind == PetDocument.Kind.OTHER and any(key in lower for key in ("versicherung", "insurance", "police", "policy")):
        kind = PetDocument.Kind.INSURANCE
    if kind == PetDocument.Kind.OTHER and any(key in lower for key in ("tierarztbericht", "arztbericht", "veterinary report", "clinical report")):
        kind = PetDocument.Kind.VET_REPORT

    return {"kind": kind, "fields": data, "field_confidences": confidence}


class UploadAdapter:
    def __init__(self, content, name, content_type):
        self._stream = io.BytesIO(content)
        self.name = name
        self.content_type = content_type
        self.size = len(content)

    def read(self, *args, **kwargs):
        return self._stream.read(*args, **kwargs)


def prepare_pet_upload(upload):
    """Validate a legacy private PetDocument through shared Document primitives."""
    raw = upload.read(MAX_DOCUMENT_BYTES + 1)
    if not raw:
        raise ValueError("Die Datei ist leer.")
    if len(raw) > MAX_DOCUMENT_BYTES:
        raise ValueError("Das Dokument darf höchstens 30 MB groß sein.")
    filename = (getattr(upload, "name", "") or "document").strip()[:180]
    content_type = (getattr(upload, "content_type", "") or "").lower()
    is_pdf = content_type == "application/pdf" or filename.lower().endswith(".pdf") or raw.startswith(b"%PDF")
    if is_pdf:
        if not raw.startswith(b"%PDF"):
            raise ValueError("Die Datei ist kein gültiges PDF.")
        try:
            PdfReader(io.BytesIO(raw))
        except Exception as exc:
            raise ValueError("Das PDF konnte nicht gelesen werden.") from exc
        stored, stored_type, warnings = raw, "application/pdf", []
    else:
        stored, stored_type, warnings = canonicalize_legacy_image(
            UploadAdapter(raw, filename, content_type)
        )
    return {
        "content": stored,
        "content_type": stored_type,
        "filename": filename,
        "sha256": hashlib.sha256(stored).hexdigest(),
        "warnings": warnings,
    }


def _ocr_image(content):
    """Compatibility name used by Pet tests; implementation is Document Core."""
    return extract_legacy_image_text(content)


def _extract_text(document):
    raw = bytes(document.content)
    warnings = list((document.extraction_data or {}).get("warnings") or [])
    if document.content_type == "application/pdf" or raw.startswith(b"%PDF"):
        reader = PdfReader(io.BytesIO(raw))
        page_count = min(len(reader.pages), MAX_PDF_PAGES)
        text = "\n".join((reader.pages[index].extract_text() or "") for index in range(page_count))[:MAX_DOCUMENT_TEXT]
        if len(reader.pages) > MAX_PDF_PAGES:
            warnings.append("page_limit")
        if not text.strip():
            warnings.append("no_embedded_text")
        return text, warnings
    try:
        return _ocr_image(raw)[:MAX_DOCUMENT_TEXT], warnings
    except Exception:
        warnings.append("ocr_failed")
        return "", warnings


def process_pet_document(document_id):
    """Run legacy PetDocument review using shared generic OCR primitives."""
    document = PetDocument.objects.filter(pk=document_id).first()
    if not document:
        return None
    PetDocument.objects.filter(pk=document.pk).update(
        extraction_status=PetDocument.ExtractionStatus.PROCESSING,
        extraction_error="",
        updated_at=timezone.now(),
    )
    try:
        text, warnings = _extract_text(document)
        extraction = extract_pet_fields(text, filename=document.filename)
        fields = extraction["fields"]
        if document.kind == PetDocument.Kind.OTHER and extraction["kind"] != PetDocument.Kind.OTHER:
            document.kind = extraction["kind"]
        if fields.get("occurred_at") and not document.occurred_at:
            from django.utils.dateparse import parse_date
            document.occurred_at = parse_date(fields["occurred_at"])
        if fields.get("provider_name") and not document.provider_name:
            document.provider_name = str(fields["provider_name"])[:180]
        document.extraction_text = text
        document.extraction_data = {**fields, "warnings": warnings}
        document.field_confidences = extraction["field_confidences"]
        document.extraction_status = PetDocument.ExtractionStatus.REVIEW
        document.extraction_error = ""
        document.save()
        return document
    except Exception:
        # Keep legacy Pet failures redacted; raw OCR/library exceptions may carry
        # file paths or extracted content.
        document.extraction_status = PetDocument.ExtractionStatus.FAILED
        document.extraction_error = "Dokument konnte nicht verarbeitet werden."
        document.save(update_fields=["extraction_status", "extraction_error", "updated_at"])
        return document
