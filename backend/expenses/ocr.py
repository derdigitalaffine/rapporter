import re
from datetime import datetime
from decimal import Decimal, InvalidOperation

MAX_OCR_TEXT_CHARS = 50_000
TOTAL_KEYWORDS = ("summe", "gesamt", "total", "zu zahlen", "endbetrag", "betrag")
NEGATIVE_KEYWORDS = ("rückgeld", "ruckgeld", "gegeben", "mwst", "steuer", "tax", "telefon", "tel.")
AMOUNT_RE = re.compile(r"(?<!\d)(\d{1,3}(?:[.,\s]\d{3})*[.,]\d{2}|\d{1,6}[.,]\d{2})(?!\d)")
DATE_PATTERNS = (
    (re.compile(r"\b(\d{1,2})[./-](\d{1,2})[./-](\d{2,4})\b"), "dmy"),
    (re.compile(r"\b(20\d{2})-(\d{1,2})-(\d{1,2})\b"), "ymd"),
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


def _extract_date(lines):
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
                return value, 0.92 if line_index < max(8, len(lines) // 2) else 0.82
            except ValueError:
                continue
    return None, 0.0


def _extract_merchant(lines):
    for index, line in enumerate(lines[:8]):
        cleaned = re.sub(r"\s+", " ", line).strip(" -*#")
        lower = cleaned.casefold()
        if len(cleaned) < 2 or any(keyword in lower for keyword in TOTAL_KEYWORDS + NEGATIVE_KEYWORDS):
            continue
        if AMOUNT_RE.fullmatch(cleaned) or re.search(r"\b\d{4,}\b", cleaned):
            continue
        alpha = sum(character.isalpha() for character in cleaned)
        if alpha < max(2, len(cleaned) // 3):
            continue
        return cleaned[:180], max(0.65, 0.9 - index * 0.04)
    return "", 0.0


def _extract_total(lines):
    candidates = []
    for index, line in enumerate(lines):
        lower = line.casefold()
        penalty = 0.45 if any(keyword in lower for keyword in NEGATIVE_KEYWORDS) else 0.0
        keyword_score = 1.0 if any(keyword in lower for keyword in TOTAL_KEYWORDS) else 0.0
        currency_score = 0.12 if ("€" in line or "eur" in lower) else 0.0
        position_score = 0.12 * (index / max(1, len(lines) - 1))
        for match in AMOUNT_RE.finditer(line):
            amount = _decimal(match.group(1))
            if amount is None or amount <= 0:
                continue
            score = 0.42 + keyword_score * 0.42 + currency_score + position_score - penalty
            candidates.append((score, index, amount, line.strip()))
    if not candidates:
        return None, 0.0, []
    candidates.sort(key=lambda item: (-item[0], -item[1], item[2]))
    best = candidates[0]
    confidence = min(0.99, max(0.25, best[0]))
    return best[2].quantize(Decimal("0.01")), confidence, [
        {"amount": str(amount.quantize(Decimal("0.01"))), "score": round(score, 3), "line": line[:180]}
        for score, _, amount, line in candidates[:5]
    ]


def parse_receipt_text(text):
    """Expense-owned receipt semantics over text produced by Documents."""
    lines = [re.sub(r"\s+", " ", line).strip() for line in (text or "").splitlines() if line.strip()]
    merchant, merchant_confidence = _extract_merchant(lines)
    date_value, date_confidence = _extract_date(lines)
    total, total_confidence, total_candidates = _extract_total(lines)
    lower_text = "\n".join(lines).casefold()
    currency = "EUR" if ("€" in (text or "") or "eur" in lower_text) else ""
    return {
        "merchant": merchant,
        "date": date_value,
        "total": total,
        "currency": currency,
        "field_confidences": {
            "merchant": round(merchant_confidence, 3),
            "date": round(date_confidence, 3),
            "total": round(total_confidence, 3),
            "currency": 0.96 if currency else 0.0,
        },
        "structured_data": {"total_candidates": total_candidates},
    }
