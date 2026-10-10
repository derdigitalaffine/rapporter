import io
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation

from django.db import close_old_connections
from django.utils import timezone
from PIL import Image, ImageEnhance, ImageOps, ImageStat, UnidentifiedImageError
import pytesseract

from .models import Expense, ReceiptExtraction

MAX_RECEIPT_BYTES = 10 * 1024 * 1024
MAX_RECEIPT_PIXELS = 25_000_000
MAX_OCR_TEXT_CHARS = 50_000
OCR_TIMEOUT_SECONDS = 20
ALLOWED_FORMATS = {"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp"}
TOTAL_KEYWORDS = ("summe", "gesamt", "total", "zu zahlen", "endbetrag", "betrag")
NEGATIVE_KEYWORDS = ("rückgeld", "ruckgeld", "gegeben", "mwst", "steuer", "tax", "telefon", "tel.")
AMOUNT_RE = re.compile(r"(?<!\d)(\d{1,3}(?:[.,\s]\d{3})*[.,]\d{2}|\d{1,6}[.,]\d{2})(?!\d)")
DATE_PATTERNS = (
    (re.compile(r"\b(\d{1,2})[./-](\d{1,2})[./-](\d{2,4})\b"), "dmy"),
    (re.compile(r"\b(20\d{2})-(\d{1,2})-(\d{1,2})\b"), "ymd"),
)


def normalize_receipt_upload(upload):
    raw = upload.read()
    if not raw:
        raise ValueError("Die Bilddatei ist leer.")
    if len(raw) > MAX_RECEIPT_BYTES:
        raise ValueError("Der Beleg darf höchstens 10 MB groß sein.")
    try:
        probe = Image.open(io.BytesIO(raw))
        image_format = (probe.format or "").upper()
        probe.verify()
        if image_format not in ALLOWED_FORMATS:
            raise ValueError("Nur JPEG-, PNG- oder WebP-Belege werden unterstützt.")
        image = Image.open(io.BytesIO(raw))
        width, height = image.size
        if width * height > MAX_RECEIPT_PIXELS:
            raise ValueError("Der Beleg hat zu viele Bildpunkte.")
        image = ImageOps.exif_transpose(image).convert("RGB")
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise ValueError("Die Datei ist kein gültiges Bild.") from exc

    warnings = []
    if min(image.size) < 700:
        warnings.append("low_resolution")
    brightness = ImageStat.Stat(ImageOps.grayscale(image)).mean[0]
    if brightness < 55:
        warnings.append("dark")

    image.thumbnail((2500, 2500), Image.Resampling.LANCZOS)
    image = ImageEnhance.Contrast(image).enhance(1.08)
    output = io.BytesIO()
    image.save(output, format="JPEG", quality=88, optimize=True)
    return output.getvalue(), "image/jpeg", warnings


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


def _ocr_image(content):
    image = Image.open(io.BytesIO(content))
    image = ImageOps.autocontrast(ImageOps.grayscale(image))
    try:
        return pytesseract.image_to_string(image, lang="deu+eng", config="--psm 6", timeout=OCR_TIMEOUT_SECONDS)
    except pytesseract.TesseractError:
        return pytesseract.image_to_string(image, config="--psm 6", timeout=OCR_TIMEOUT_SECONDS)


def process_receipt_extraction(extraction_id):
    close_old_connections()
    try:
        claimed = ReceiptExtraction.objects.filter(
            id=extraction_id,
            status=ReceiptExtraction.Status.QUEUED,
        ).update(status=ReceiptExtraction.Status.PROCESSING, error="", updated_at=timezone.now())
        if not claimed:
            return ReceiptExtraction.objects.filter(id=extraction_id).first()

        extraction = ReceiptExtraction.objects.select_related("expense").filter(id=extraction_id).first()
        if not extraction:
            return None
        expense = extraction.expense
        Expense.objects.filter(id=expense.id, receipt_content__isnull=False).update(
            receipt_status=Expense.ReceiptStatus.PROCESSING,
            updated_at=timezone.now(),
        )

        try:
            content = bytes(expense.receipt_content or b"")
            if not content:
                raise ValueError("Receipt image is no longer available.")
            text = _ocr_image(content)[:MAX_OCR_TEXT_CHARS]
            parsed = parse_receipt_text(text)
            processed_at = timezone.now()
            updated = ReceiptExtraction.objects.filter(id=extraction_id, expense_id=expense.id).update(
                raw_text=text,
                merchant=parsed["merchant"],
                date=parsed["date"],
                total=parsed["total"],
                currency=parsed["currency"],
                field_confidences=parsed["field_confidences"],
                structured_data={**(extraction.structured_data or {}), **parsed["structured_data"]},
                status=ReceiptExtraction.Status.REVIEW,
                processed_at=processed_at,
                error="",
                updated_at=processed_at,
            )
            if not updated:
                return None

            expense_updates = {
                "receipt_status": Expense.ReceiptStatus.REVIEW,
                "updated_at": processed_at,
            }
            if parsed["merchant"] and not expense.merchant:
                expense_updates["merchant"] = parsed["merchant"]
                expense_updates["title"] = parsed["merchant"]
            if parsed["date"]:
                expense_updates["occurred_at"] = timezone.make_aware(datetime.combine(parsed["date"], datetime.min.time()))
            if parsed["total"] is not None:
                expense_updates["total_amount"] = parsed["total"]
            if parsed["currency"]:
                expense_updates["currency"] = parsed["currency"]
            Expense.objects.filter(id=expense.id, receipt_content__isnull=False).update(**expense_updates)
            return ReceiptExtraction.objects.filter(id=extraction_id).first()
        except Exception as exc:
            processed_at = timezone.now()
            ReceiptExtraction.objects.filter(id=extraction_id).update(
                status=ReceiptExtraction.Status.FAILED,
                processed_at=processed_at,
                error=str(exc)[:500],
                updated_at=processed_at,
            )
            Expense.objects.filter(id=expense.id, receipt_content__isnull=False).update(
                receipt_status=Expense.ReceiptStatus.FAILED,
                updated_at=processed_at,
            )
            return ReceiptExtraction.objects.filter(id=extraction_id).first()
    finally:
        close_old_connections()


def enqueue_receipt_extraction(extraction_id):
    """Wake-up compatibility hook; durable workers own OCR execution.

    The queued database row is the source of truth. Request processes must never
    spawn OCR threads. Existing callers may keep invoking this hook while the
    legacy receipt model is migrated to the shared document-processing core.
    """
    return None
