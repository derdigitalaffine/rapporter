"""Receipt-domain intelligence layered on the shared Document Processing Core.

The documents app owns image/PDF normalization, OCR, geometry and OCR confidence.
This module owns only receipt semantics, candidate ranking and reconciliation.
Raw evidence is preserved alongside normalized values so review can explain every
suggestion without creating a second OCR truth.
"""
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation

EXTRACTOR_VERSION = "receipt-v2"
STRUCTURED_SCHEMA_VERSION = 2

STRONG_TOTAL_KEYWORDS = (
    "zu zahlen",
    "zahlbetrag",
    "gesamtbetrag",
    "endsumme",
    "endbetrag",
    "gesamt",
    "summe",
    "total",
)
WEAK_TOTAL_KEYWORDS = ("betrag",)
SUBTOTAL_KEYWORDS = ("zwischensumme", "subtotal", "nettobetrag", "netto summe", "netto", "warenwert")
TAX_KEYWORDS = ("mwst", "mehrwertsteuer", "umsatzsteuer", "ust", "tax", "vat")
PAYMENT_KEYWORDS = (
    "rückgeld",
    "ruckgeld",
    "change",
    "gegeben",
    "erhalten",
    "bar bezahlt",
    "cash",
    "karte",
    "card",
    "girocard",
    "visa",
    "mastercard",
    "zahlart",
    "zahlung",
)
NOISE_KEYWORDS = ("telefon", "tel.", "tel:", "fax", "www.", "http://", "https://")
SUMMARY_KEYWORDS = STRONG_TOTAL_KEYWORDS + WEAK_TOTAL_KEYWORDS + SUBTOTAL_KEYWORDS + TAX_KEYWORDS + PAYMENT_KEYWORDS

AMOUNT_RE = re.compile(r"(?<!\d)(\d{1,3}(?:[.,\s]\d{3})*[.,]\d{2}|\d{1,6}[.,]\d{2})(?!\d)")
DATE_PATTERNS = (
    (re.compile(r"\b(\d{1,2})[./-](\d{1,2})[./-](\d{2,4})\b"), "dmy"),
    (re.compile(r"\b(20\d{2})-(\d{1,2})-(\d{1,2})\b"), "ymd"),
)
TIME_RE = re.compile(r"(?<!\d)([01]?\d|2[0-3]):([0-5]\d)(?::([0-5]\d))?(?!\d)")
RECEIPT_ID_RE = re.compile(
    r"\b(?:beleg(?:\s*[- ]?\s*(?:nr|nummer))?|bon(?:\s*[- ]?\s*(?:nr|nummer))?|"
    r"receipt(?:\s*(?:no|nr|number))?|trans(?:aktion)?s?(?:\s*[- ]?\s*(?:id|nr|nummer))?)"
    r"\.?\s*[:#]?\s*([A-Z0-9][A-Z0-9./_-]{2,})",
    re.IGNORECASE,
)
QUANTITY_RE = re.compile(
    r"(?<!\d)(\d+(?:[.,]\d+)?)\s*[x×]\s*(\d{1,6}[.,]\d{2})(?!\d)",
    re.IGNORECASE,
)

CURRENCY_SIGNALS = (
    ("EUR", re.compile(r"(?:€|\bEUR\b)", re.IGNORECASE), 0.98),
    ("USD", re.compile(r"\bUSD\b", re.IGNORECASE), 0.98),
    ("GBP", re.compile(r"(?:£|\bGBP\b)", re.IGNORECASE), 0.98),
    ("CHF", re.compile(r"\bCHF\b", re.IGNORECASE), 0.98),
)


def _decimal(value):
    try:
        normalized = value.replace(" ", "")
        if "," in normalized and "." in normalized:
            decimal_separator = "," if normalized.rfind(",") > normalized.rfind(".") else "."
            thousands_separator = "." if decimal_separator == "," else ","
            normalized = normalized.replace(thousands_separator, "").replace(decimal_separator, ".")
        else:
            normalized = normalized.replace(",", ".")
        return Decimal(normalized)
    except (InvalidOperation, AttributeError):
        return None


def _money(value):
    return str(value.quantize(Decimal("0.01"))) if value is not None else None


def _contains(line, keywords):
    lower = line.casefold()
    for keyword in keywords:
        if re.fullmatch(r"[\wäöüß]+", keyword, re.IGNORECASE):
            if re.search(rf"(?<!\w){re.escape(keyword)}(?!\w)", lower, re.IGNORECASE):
                return keyword
        elif keyword in lower:
            return keyword
    return ""


def _normalize_lines(text):
    return [re.sub(r"\s+", " ", line).strip() for line in (text or "").splitlines() if line.strip()]


def _extract_currency(text):
    matches = []
    for code, pattern, confidence in CURRENCY_SIGNALS:
        match = pattern.search(text or "")
        if match:
            matches.append((match.start(), code, confidence, match.group(0)))
    if not matches:
        return "", 0.0, None
    matches.sort(key=lambda item: item[0])
    _, code, confidence, raw = matches[0]
    return code, confidence, {"raw": raw, "normalized": code, "semantic_confidence": confidence}


def _extract_date_time(lines):
    date_candidates = []
    time_candidates = []
    for line_index, line in enumerate(lines):
        for pattern, mode in DATE_PATTERNS:
            match = pattern.search(line)
            if not match:
                continue
            try:
                if mode == "dmy":
                    day, month, year = match.groups()
                    year = int(year)
                    if year < 100:
                        year += 2000
                    value = datetime(year, int(month), int(day)).date()
                else:
                    year, month, day = match.groups()
                    value = datetime(int(year), int(month), int(day)).date()
            except ValueError:
                continue
            score = 0.94 if line_index < max(8, len(lines) // 2) else 0.84
            if "datum" in line.casefold() or "date" in line.casefold():
                score = min(0.99, score + 0.04)
            date_candidates.append((score, line_index, value, match.group(0), line))

            time_match = TIME_RE.search(line)
            if time_match:
                hour, minute, second = time_match.groups()
                value_time = datetime(2000, 1, 1, int(hour), int(minute), int(second or 0)).time()
                time_candidates.append((0.96, line_index, value_time, time_match.group(0), line))

    if date_candidates and not time_candidates:
        date_line = min(date_candidates, key=lambda item: (-item[0], item[1]))[1]
        for line_index in range(max(0, date_line - 1), min(len(lines), date_line + 3)):
            match = TIME_RE.search(lines[line_index])
            if not match:
                continue
            hour, minute, second = match.groups()
            value_time = datetime(2000, 1, 1, int(hour), int(minute), int(second or 0)).time()
            distance = abs(line_index - date_line)
            time_candidates.append((0.9 - distance * 0.08, line_index, value_time, match.group(0), lines[line_index]))

    date_candidates.sort(key=lambda item: (-item[0], item[1]))
    time_candidates.sort(key=lambda item: (-item[0], abs(item[1] - (date_candidates[0][1] if date_candidates else item[1]))))
    date_best = date_candidates[0] if date_candidates else None
    time_best = time_candidates[0] if time_candidates else None
    return (
        date_best[2] if date_best else None,
        date_best[0] if date_best else 0.0,
        time_best[2] if time_best else None,
        time_best[0] if time_best else 0.0,
        {
            "date": (
                {
                    "raw": date_best[3],
                    "normalized": date_best[2].isoformat(),
                    "line": date_best[4][:180],
                    "line_index": date_best[1],
                    "semantic_confidence": round(date_best[0], 3),
                }
                if date_best
                else None
            ),
            "time": (
                {
                    "raw": time_best[3],
                    "normalized": time_best[2].isoformat(),
                    "line": time_best[4][:180],
                    "line_index": time_best[1],
                    "semantic_confidence": round(time_best[0], 3),
                }
                if time_best
                else None
            ),
        },
    )


def _extract_merchant(lines):
    candidates = []
    for index, line in enumerate(lines[:8]):
        cleaned = re.sub(r"\s+", " ", line).strip(" -*#")
        lower = cleaned.casefold()
        if len(cleaned) < 2 or _contains(lower, SUMMARY_KEYWORDS):
            continue
        if DATE_PATTERNS[0][0].search(cleaned) or DATE_PATTERNS[1][0].search(cleaned) or TIME_RE.search(cleaned):
            continue
        if AMOUNT_RE.fullmatch(cleaned) or RECEIPT_ID_RE.search(cleaned):
            continue
        alpha = sum(character.isalpha() for character in cleaned)
        if alpha < max(2, len(cleaned) // 3):
            continue
        score = 0.92 - index * 0.055
        if any(keyword in lower for keyword in NOISE_KEYWORDS):
            score -= 0.35
        if re.search(r"\b\d{4,5}\b", cleaned) or any(token in lower for token in ("straße", "strasse", "str.", "platz", "weg ")):
            score -= 0.18
        upper_alpha = sum(character.isupper() for character in cleaned if character.isalpha())
        if alpha and upper_alpha / alpha >= 0.6:
            score += 0.04
        if score >= 0.45:
            candidates.append((score, index, cleaned[:180], line))
    if not candidates:
        return "", 0.0, None
    candidates.sort(key=lambda item: (-item[0], item[1]))
    score, index, value, raw = candidates[0]
    confidence = min(0.97, max(0.45, score))
    return value, confidence, {
        "raw": raw[:180],
        "normalized": value,
        "line_index": index,
        "semantic_confidence": round(confidence, 3),
    }


def _line_amounts(line):
    amounts = []
    for match in AMOUNT_RE.finditer(line):
        amount = _decimal(match.group(1))
        if amount is not None and amount > 0:
            amounts.append((match, amount.quantize(Decimal("0.01"))))
    return amounts


def _extract_total(lines):
    candidates = []
    for index, line in enumerate(lines):
        lower = line.casefold()
        strong_label = _contains(lower, STRONG_TOTAL_KEYWORDS)
        weak_label = _contains(lower, WEAK_TOTAL_KEYWORDS)
        subtotal_label = _contains(lower, SUBTOTAL_KEYWORDS)
        tax_label = _contains(lower, TAX_KEYWORDS)
        payment_label = _contains(lower, PAYMENT_KEYWORDS)
        noise_label = _contains(lower, NOISE_KEYWORDS)
        currency_signal = bool(re.search(r"(?:€|\bEUR\b|\bUSD\b|\bGBP\b|\bCHF\b)", line, re.IGNORECASE))
        position = index / max(1, len(lines) - 1)
        for _, amount in _line_amounts(line):
            score = 0.30 + 0.12 * position
            reasons = []
            if strong_label:
                score += 0.50
                reasons.append(f"total:{strong_label}")
            elif weak_label:
                score += 0.24
                reasons.append(f"weak-total:{weak_label}")
            if currency_signal:
                score += 0.08
                reasons.append("currency")
            if subtotal_label:
                score -= 0.55
                reasons.append(f"subtotal:{subtotal_label}")
            if tax_label:
                score -= 0.62
                reasons.append(f"tax:{tax_label}")
            if payment_label:
                score -= 0.22 if strong_label else 0.68
                reasons.append(f"payment:{payment_label}")
            if noise_label or RECEIPT_ID_RE.search(line):
                score -= 0.55
                reasons.append("noise-or-id")
            score = max(0.0, min(0.99, score))
            candidates.append(
                {
                    "amount_value": amount,
                    "amount": _money(amount),
                    "score": score,
                    "line_index": index,
                    "line": line[:180],
                    "reasons": reasons,
                }
            )
    candidates.sort(key=lambda item: (-item["score"], -item["line_index"], item["amount_value"]))
    public_candidates = [
        {
            "amount": item["amount"],
            "score": round(item["score"], 3),
            "line_index": item["line_index"],
            "line": item["line"],
            "reasons": item["reasons"],
        }
        for item in candidates[:8]
    ]
    if not candidates or candidates[0]["score"] < 0.45:
        return None, 0.0, public_candidates, False, None

    best = candidates[0]
    plausible = [
        item
        for item in candidates[1:]
        if item["amount_value"] != best["amount_value"]
        and item["score"] >= 0.55
        and best["score"] - item["score"] <= 0.08
    ]
    ambiguous = bool(plausible)
    confidence = max(0.25, min(0.99, best["score"] - (0.18 if ambiguous else 0.0)))
    evidence = {
        "raw": best["line"],
        "normalized": best["amount"],
        "line_index": best["line_index"],
        "semantic_confidence": round(confidence, 3),
        "ambiguous": ambiguous,
    }
    return best["amount_value"], confidence, public_candidates, ambiguous, evidence


def _extract_explicit_amount(lines, keywords, field_name):
    candidates = []
    for index, line in enumerate(lines):
        label = _contains(line, keywords)
        if not label:
            continue
        amounts = _line_amounts(line)
        if not amounts:
            continue
        _, amount = amounts[-1]
        score = 0.91
        if len(amounts) > 1:
            score -= 0.05
        if field_name == "subtotal" and _contains(line, STRONG_TOTAL_KEYWORDS):
            score -= 0.35
        candidates.append((score, index, amount, line, label))
    if not candidates:
        return None, 0.0, None
    candidates.sort(key=lambda item: (-item[0], -item[1]))
    score, index, amount, line, label = candidates[0]
    return amount, score, {
        "raw": line[:180],
        "normalized": _money(amount),
        "line_index": index,
        "matched_label": label,
        "semantic_confidence": round(score, 3),
    }


def _extract_receipt_id(lines):
    for index, line in enumerate(lines):
        match = RECEIPT_ID_RE.search(line)
        if not match:
            continue
        value = match.group(1).strip(" .:-")
        if len(value) < 3:
            continue
        return value[:80], 0.92, {
            "raw": match.group(0)[:180],
            "normalized": value[:80],
            "line": line[:180],
            "line_index": index,
            "semantic_confidence": 0.92,
        }
    return "", 0.0, None


def _extract_line_items(lines):
    items = []
    for index, line in enumerate(lines):
        lower = line.casefold()
        if _contains(lower, SUMMARY_KEYWORDS + NOISE_KEYWORDS) or RECEIPT_ID_RE.search(line):
            continue
        if DATE_PATTERNS[0][0].search(line) or DATE_PATTERNS[1][0].search(line) or TIME_RE.search(line):
            continue
        amounts = _line_amounts(line)
        if not amounts:
            continue
        match, amount = amounts[-1]
        suffix = line[match.end():].strip()
        if suffix and not re.fullmatch(r"(?:€|EUR|[A-D]\*?)", suffix, re.IGNORECASE):
            continue
        description = line[:match.start()].strip(" .-*#")
        alpha = sum(character.isalpha() for character in description)
        if alpha < 2 or len(description) < 3:
            continue
        quantity = None
        unit_price = None
        quantity_match = QUANTITY_RE.search(description)
        if quantity_match:
            quantity = _decimal(quantity_match.group(1))
            unit_price = _decimal(quantity_match.group(2))
        confidence = 0.76
        if suffix:
            confidence += 0.04
        if quantity is not None and unit_price is not None:
            confidence += 0.05
        item = {
            "description": description[:180],
            "total": _money(amount),
            "raw": line[:220],
            "line_index": index,
            "semantic_confidence": round(min(0.9, confidence), 3),
        }
        if quantity is not None:
            item["quantity"] = str(quantity.normalize())
        if unit_price is not None:
            item["unit_price"] = _money(unit_price)
        items.append(item)
        if len(items) >= 50:
            break
    return items


def _within(actual, expected):
    tolerance = max(Decimal("0.02"), abs(expected) * Decimal("0.001"))
    delta = actual - expected
    return abs(delta) <= tolerance, delta, tolerance


def _reconcile(items, subtotal, subtotal_evidence, tax, total):
    checks = []
    item_sum = sum((Decimal(item["total"]) for item in items), Decimal("0.00")) if items else None
    subtotal_label = (subtotal_evidence or {}).get("matched_label", "")

    def add_check(kind, actual, expected, *, authoritative):
        matched, delta, tolerance = _within(actual, expected)
        checks.append(
            {
                "kind": kind,
                "actual": _money(actual),
                "expected": _money(expected),
                "delta": _money(delta),
                "tolerance": _money(tolerance),
                "matched": matched,
                "authoritative": authoritative,
            }
        )

    if item_sum is not None and subtotal is not None and "netto" not in subtotal_label:
        add_check("line_items_vs_subtotal", item_sum, subtotal, authoritative=True)
    elif item_sum is not None and total is not None:
        add_check("line_items_vs_total", item_sum, total, authoritative=False)

    if subtotal is not None and tax is not None and total is not None and "netto" in subtotal_label:
        add_check("net_subtotal_plus_tax_vs_total", subtotal + tax, total, authoritative=True)

    authoritative = [check for check in checks if check["authoritative"]]
    if any(not check["matched"] for check in authoritative):
        status = "mismatch"
    elif authoritative and all(check["matched"] for check in authoritative):
        status = "matched"
    elif checks:
        status = "partial"
    else:
        status = "insufficient"
    return {
        "status": status,
        "item_sum": _money(item_sum),
        "checks": checks,
    }


def parse_receipt_text(text, *, ocr_confidence=None):
    lines = _normalize_lines(text)
    merchant, merchant_confidence, merchant_evidence = _extract_merchant(lines)
    date_value, date_confidence, time_value, time_confidence, temporal_evidence = _extract_date_time(lines)
    currency, currency_confidence, currency_evidence = _extract_currency(text or "")
    total, total_confidence, total_candidates, total_ambiguous, total_evidence = _extract_total(lines)
    subtotal, subtotal_confidence, subtotal_evidence = _extract_explicit_amount(lines, SUBTOTAL_KEYWORDS, "subtotal")
    tax, tax_confidence, tax_evidence = _extract_explicit_amount(lines, TAX_KEYWORDS, "tax")
    receipt_id, receipt_id_confidence, receipt_id_evidence = _extract_receipt_id(lines)
    line_items = _extract_line_items(lines)
    reconciliation = _reconcile(line_items, subtotal, subtotal_evidence, tax, total)

    review_reasons = []
    if ocr_confidence is not None and ocr_confidence < 0.55:
        review_reasons.append("ocr_confidence_low")
    if total is None:
        review_reasons.append("total_missing")
    elif total_confidence < 0.65:
        review_reasons.append("total_confidence_low")
    if total_ambiguous:
        review_reasons.append("total_ambiguous")
    if reconciliation["status"] == "mismatch":
        review_reasons.append("reconciliation_mismatch")

    field_confidences = {
        "merchant": round(merchant_confidence, 3),
        "date": round(date_confidence, 3),
        "time": round(time_confidence, 3),
        "currency": round(currency_confidence, 3),
        "total": round(total_confidence, 3),
        "subtotal": round(subtotal_confidence, 3),
        "tax": round(tax_confidence, 3),
        "receipt_id": round(receipt_id_confidence, 3),
    }
    semantic_values = [value for value in field_confidences.values() if value > 0]
    semantic_confidence = round(sum(semantic_values) / len(semantic_values), 3) if semantic_values else 0.0

    return {
        "merchant": merchant,
        "date": date_value,
        "time": time_value,
        "total": total,
        "currency": currency,
        "field_confidences": field_confidences,
        "subtotal": subtotal,
        "tax": tax,
        "receipt_id": receipt_id,
        "needs_review": bool(review_reasons),
        "review_reasons": review_reasons,
        "structured_data": {
            "schema_version": STRUCTURED_SCHEMA_VERSION,
            "extractor_version": EXTRACTOR_VERSION,
            "ocr_confidence": round(float(ocr_confidence), 3) if ocr_confidence is not None else None,
            "semantic_confidence": semantic_confidence,
            "fields": {
                "merchant": merchant_evidence,
                "date": temporal_evidence["date"],
                "time": temporal_evidence["time"],
                "currency": currency_evidence,
                "total": total_evidence,
                "subtotal": subtotal_evidence,
                "tax": tax_evidence,
                "receipt_id": receipt_id_evidence,
            },
            "total_candidates": total_candidates,
            "line_items": line_items,
            "reconciliation": reconciliation,
            "review": {
                "needs_review": bool(review_reasons),
                "reasons": review_reasons,
            },
        },
    }
