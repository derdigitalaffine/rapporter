"""Deterministic local document classification and typed field extraction.

No network, cloud model or LLM is involved. Rules intentionally prefer explicit
labels over guesses so review suggestions carry useful provenance and low false-
positive risk.
"""
from dataclasses import dataclass
import re

EXTRACTOR_VERSION = "rules-v1"

TYPE_RULES = {
    "receipt": (("kassenbon", 3), ("bon-nr", 3), ("rückgeld", 2), ("ruckgeld", 2), ("kasse", 1), ("mwst", 1)),
    "invoice": (("rechnung", 3), ("rechnungsnummer", 3), ("zahlungsziel", 2), ("netto", 1), ("brutto", 1), ("iban", 1)),
    "contract": (("vertrag", 3), ("vertragsnummer", 3), ("vertragsbeginn", 2), ("laufzeit", 2), ("kündigungsfrist", 2), ("kuendigungsfrist", 2)),
    "official_letter": (("aktenzeichen", 3), ("bescheid", 3), ("widerspruch", 2), ("sachbearbeiter", 2), ("behörde", 2), ("behoerde", 2)),
    "warranty": (("garantie", 3), ("gewährleistung", 3), ("gewaehrleistung", 3), ("seriennummer", 2), ("garantiezeit", 2)),
    "school": (("elternbrief", 3), ("schuljahr", 2), ("schule", 2), ("schüler", 2), ("schueler", 2), ("klasse", 1)),
    "medical": (("arzt", 2), ("arztpraxis", 3), ("patient", 2), ("impfung", 3), ("rezept", 2), ("diagnose", 2)),
    "pet": (("tierarzt", 3), ("chipnummer", 3), ("heimtierausweis", 3), ("hund", 1), ("katze", 1)),
    "identity": (("personalausweis", 4), ("reisepass", 4), ("ausweisnummer", 3), ("passnummer", 3), ("gültig bis", 2), ("gueltig bis", 2)),
}

DATE_VALUE = r"(?P<value>\d{1,2}[./-]\d{1,2}[./-]\d{2,4}|20\d{2}-\d{1,2}-\d{1,2})"
AMOUNT_VALUE = r"(?P<value>\d{1,3}(?:[.\s]\d{3})*(?:,\d{2})|\d{1,6}[.,]\d{2})\s*(?:€|EUR)?"
REFERENCE_VALUE = r"(?P<value>[A-Z0-9][A-Z0-9./_-]{2,31})"


@dataclass(frozen=True)
class Classification:
    kind: str
    confidence: float
    evidence_text: str = ""
    page: int | None = None


def _pages(result):
    pages = []
    for field in result.fields:
        if field.get("key") != "text.page":
            continue
        value = field.get("value_json") or {}
        text = str(value.get("text") or field.get("evidence_text") or "")
        pages.append((field.get("page"), text))
    if not pages and result.text:
        pages.append((None, result.text))
    return pages


def classify_result(result):
    page_rows = _pages(result)
    full_text = "\n".join(text for _, text in page_rows).casefold()
    scores = {}
    evidence = {}
    for kind, rules in TYPE_RULES.items():
        score = 0
        matched = []
        for term, weight in rules:
            if term in full_text:
                score += weight
                matched.append(term)
        scores[kind] = score
        if matched:
            evidence[kind] = matched
    best_kind = max(scores, key=scores.get) if scores else "generic"
    best_score = scores.get(best_kind, 0)
    ordered = sorted(scores.values(), reverse=True)
    runner_up = ordered[1] if len(ordered) > 1 else 0
    if best_score < 2 or (best_score == runner_up and best_score < 4):
        return Classification("generic", 0.5)

    matched_terms = evidence[best_kind]
    source_page = None
    source_line = ""
    for page, text in page_rows:
        for line in text.splitlines():
            lower = line.casefold()
            if any(term in lower for term in matched_terms):
                source_page = page
                source_line = line.strip()[:500]
                break
        if source_line:
            break
    margin = max(0, best_score - runner_up)
    confidence = min(0.98, 0.62 + min(best_score, 8) * 0.035 + min(margin, 4) * 0.025)
    return Classification(best_kind, round(confidence, 4), source_line, source_page)


def _field(key, value, confidence, page, evidence, *, source_type="explicit"):
    return {
        "key": key,
        "value_json": {"value": value},
        "confidence": confidence,
        "page": page,
        "bbox": None,
        "evidence_text": evidence[:2000],
        "source_type": source_type,
        "extractor_version": EXTRACTOR_VERSION,
    }


def _labelled_match(result, key, labels, value_pattern, *, confidence=0.94):
    label_pattern = "|".join(re.escape(label) for label in labels)
    regex = re.compile(rf"(?i)\b(?:{label_pattern})\b\s*(?:[:#]|nr\.?|nummer)?\s*{value_pattern}")
    for page, text in _pages(result):
        for line in text.splitlines():
            match = regex.search(line)
            if match:
                return _field(key, match.group("value").strip(), confidence, page, line.strip())
    return None


def _date(result, key="document.date", labels=("datum", "belegdatum", "rechnungsdatum")):
    return _labelled_match(result, key, labels, DATE_VALUE, confidence=0.95)


def _amount(result):
    return _labelled_match(
        result,
        "amount.total",
        ("gesamt", "summe", "total", "endbetrag", "zu zahlen", "brutto"),
        AMOUNT_VALUE,
        confidence=0.96,
    )


def _reference(result, key, labels):
    return _labelled_match(result, key, labels, REFERENCE_VALUE, confidence=0.96)


def extract_receipt(result):
    return [value for value in (_amount(result), _date(result, labels=("datum", "belegdatum")), _reference(result, "receipt.number", ("bon-nr", "bon nr", "belegnummer"))) if value]


def extract_invoice(result):
    return [value for value in (_amount(result), _date(result, labels=("rechnungsdatum", "datum")), _reference(result, "invoice.number", ("rechnungsnummer", "rechnung nr", "rechnung-nr"))) if value]


def extract_contract(result):
    return [value for value in (
        _reference(result, "contract.number", ("vertragsnummer", "vertrag nr", "vertrag-nr")),
        _date(result, "contract.start_date", ("vertragsbeginn", "beginn")),
        _date(result, "contract.end_date", ("vertragsende", "ende")),
    ) if value]


def extract_official_letter(result):
    return [value for value in (
        _reference(result, "letter.reference", ("aktenzeichen", "geschäftszeichen", "geschaeftszeichen")),
        _date(result, labels=("datum",)),
    ) if value]


def extract_warranty(result):
    return [value for value in (
        _reference(result, "warranty.serial_number", ("seriennummer", "serial", "s/n")),
        _date(result, "warranty.purchase_date", ("kaufdatum", "datum")),
    ) if value]


def extract_school(result):
    return [value for value in (
        _labelled_match(result, "school.class", ("klasse",), r"(?P<value>[1-9][0-3]?[a-zA-Z]?)", confidence=0.92),
        _date(result, labels=("datum",)),
    ) if value]


def extract_medical(result):
    # Keep the generic engine deliberately narrow: domain-specific diagnosis or
    # treatment semantics belong to the medical domain/review UI, not OCR core.
    return [value for value in (_date(result, labels=("datum", "behandlungsdatum", "impfdatum")),) if value]


def extract_pet(result):
    return [value for value in (
        _reference(result, "pet.microchip", ("chipnummer", "transponder", "mikrochip")),
        _date(result, labels=("datum", "impfdatum")),
    ) if value]


def extract_identity(result):
    return [value for value in (
        _reference(result, "identity.document_number", ("ausweisnummer", "passnummer", "dokumentnummer")),
        _date(result, "identity.expires_at", ("gültig bis", "gueltig bis", "ablaufdatum")),
    ) if value]


EXTRACTOR_REGISTRY = {
    "receipt": extract_receipt,
    "invoice": extract_invoice,
    "contract": extract_contract,
    "official_letter": extract_official_letter,
    "warranty": extract_warranty,
    "school": extract_school,
    "medical": extract_medical,
    "pet": extract_pet,
    "identity": extract_identity,
    "generic": lambda result: [],
}


def enrich_extraction(result):
    classification = classify_result(result)
    result.quality_data = {
        **(result.quality_data or {}),
        "classification": {
            "kind": classification.kind,
            "confidence": classification.confidence,
            "extractor_version": EXTRACTOR_VERSION,
        },
    }
    result.fields.append(
        _field(
            "document.type",
            classification.kind,
            classification.confidence,
            classification.page,
            classification.evidence_text,
            source_type="derived",
        )
    )
    result.fields.extend(EXTRACTOR_REGISTRY[classification.kind](result))
    return result
