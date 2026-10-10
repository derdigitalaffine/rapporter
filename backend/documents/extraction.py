"""Local document text extraction with provenance.

The pipeline deliberately has no network/LLM dependency. Born-digital PDF pages
use their embedded text. Image documents and image-only PDF pages use local
Tesseract TSV output so confidence and bounding boxes remain available for
review and future typed extractors.
"""
from dataclasses import dataclass, field
import io
import statistics

from PIL import Image, ImageOps, UnidentifiedImageError
from pypdf import PdfReader
from pypdf.errors import PdfReadError
import pytesseract
from pytesseract import Output

from .storage import open_canonical

MAX_TEXT_CHARS = 250_000
MAX_OCR_WORDS_PER_PAGE = 1000
MIN_EMBEDDED_TEXT_CHARS = 24
OCR_TIMEOUT_SECONDS = 30


class ProcessingError(Exception):
    def __init__(self, code, safe_message, *, retryable=False):
        super().__init__(safe_message)
        self.code = code
        self.safe_message = safe_message
        self.retryable = retryable


@dataclass
class ExtractionResult:
    text: str
    extractor: str
    language: str = ""
    quality_data: dict = field(default_factory=dict)
    fields: list = field(default_factory=list)
    needs_review: bool = True


def _normalise_text(value):
    lines = [" ".join(line.split()) for line in (value or "").splitlines()]
    return "\n".join(line for line in lines if line).strip()


def _psm_for(image):
    width, height = image.size
    # Dense/narrow receipt-like pages benefit from a single text block, while
    # document pages should let Tesseract discover their layout automatically.
    if height > width * 1.35:
        return 6
    return 3


def _ocr_image(image, page_number):
    image = ImageOps.autocontrast(ImageOps.grayscale(image))
    config = f"--psm {_psm_for(image)}"
    try:
        data = pytesseract.image_to_data(
            image,
            lang="deu+eng",
            config=config,
            timeout=OCR_TIMEOUT_SECONDS,
            output_type=Output.DICT,
        )
        language = "deu+eng"
    except pytesseract.TesseractError:
        try:
            data = pytesseract.image_to_data(
                image,
                config=config,
                timeout=OCR_TIMEOUT_SECONDS,
                output_type=Output.DICT,
            )
            language = "default"
        except (pytesseract.TesseractError, RuntimeError, OSError) as exc:
            raise ProcessingError("ocr_failed", "Lokale OCR konnte die Seite nicht verarbeiten.", retryable=True) from exc
    except (RuntimeError, OSError) as exc:
        raise ProcessingError("ocr_failed", "Lokale OCR konnte die Seite nicht verarbeiten.", retryable=True) from exc

    words = []
    confidences = []
    line_parts = []
    last_line_key = None
    text_lines = []
    count = len(data.get("text", []))
    for index in range(count):
        token = str(data["text"][index] or "").strip()
        if not token:
            continue
        try:
            confidence = max(0.0, min(100.0, float(data["conf"][index]))) / 100.0
        except (TypeError, ValueError):
            confidence = 0.0
        line_key = (
            data.get("block_num", [0] * count)[index],
            data.get("par_num", [0] * count)[index],
            data.get("line_num", [0] * count)[index],
        )
        if last_line_key is not None and line_key != last_line_key and line_parts:
            text_lines.append(" ".join(line_parts))
            line_parts = []
        last_line_key = line_key
        line_parts.append(token)
        confidences.append(confidence)
        if len(words) < MAX_OCR_WORDS_PER_PAGE:
            words.append(
                {
                    "text": token,
                    "confidence": round(confidence, 4),
                    "bbox": [
                        int(data["left"][index]),
                        int(data["top"][index]),
                        int(data["width"][index]),
                        int(data["height"][index]),
                    ],
                }
            )
    if line_parts:
        text_lines.append(" ".join(line_parts))
    text = _normalise_text("\n".join(text_lines))
    mean_confidence = statistics.fmean(confidences) if confidences else 0.0
    return {
        "page": page_number,
        "text": text,
        "language": language,
        "confidence": round(mean_confidence, 4),
        "width": image.width,
        "height": image.height,
        "words": words,
        "word_count": len(confidences),
        "psm": _psm_for(image),
    }


def _page_field(page_data, source):
    return {
        "key": "text.page",
        "value_json": {"text": page_data["text"], "source": source},
        "confidence": page_data.get("confidence", 1.0),
        "page": page_data["page"],
        "bbox": [0, 0, page_data.get("width", 0), page_data.get("height", 0)] if page_data.get("width") else None,
        "evidence_text": page_data["text"][:2000],
        "source_type": "explicit",
    }


def _extract_image(handle):
    try:
        with Image.open(handle) as source:
            source.load()
            page = _ocr_image(source.convert("RGB"), 1)
    except ProcessingError:
        raise
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise ProcessingError("image_decode_failed", "Das gespeicherte Bild konnte nicht gelesen werden.") from exc
    return ExtractionResult(
        text=page["text"][:MAX_TEXT_CHARS],
        extractor="tesseract-tsv",
        language=page["language"],
        quality_data={
            "pages": [{key: value for key, value in page.items() if key != "text"}],
            "source": "ocr",
        },
        fields=[_page_field(page, "ocr")],
        needs_review=True,
    )


def _extract_pdf(handle):
    try:
        reader = PdfReader(handle, strict=False)
    except (PdfReadError, ValueError, OSError, EOFError) as exc:
        raise ProcessingError("pdf_decode_failed", "Das gespeicherte PDF konnte nicht gelesen werden.") from exc
    page_results = []
    fields = []
    languages = set()
    used_ocr = False
    for page_number, page in enumerate(reader.pages, start=1):
        embedded = _normalise_text(page.extract_text() or "")
        if len(embedded) >= MIN_EMBEDDED_TEXT_CHARS:
            page_data = {
                "page": page_number,
                "text": embedded,
                "confidence": 1.0,
                "source": "embedded",
                "word_count": len(embedded.split()),
            }
            page_results.append(page_data)
            fields.append(_page_field(page_data, "embedded"))
            continue

        ocr_pages = []
        try:
            page_images = list(page.images)
        except Exception:
            page_images = []
        for page_image in page_images:
            try:
                image = page_image.image.convert("RGB")
            except Exception:
                try:
                    image = Image.open(io.BytesIO(page_image.data)).convert("RGB")
                except Exception:
                    continue
            ocr_pages.append(_ocr_image(image, page_number))
        if ocr_pages:
            used_ocr = True
            languages.update(item["language"] for item in ocr_pages if item["language"])
            combined_text = _normalise_text("\n".join(item["text"] for item in ocr_pages))
            all_words = [word for item in ocr_pages for word in item["words"]][:MAX_OCR_WORDS_PER_PAGE]
            weighted = [item["confidence"] for item in ocr_pages if item["word_count"]]
            page_data = {
                "page": page_number,
                "text": combined_text,
                "confidence": round(statistics.fmean(weighted), 4) if weighted else 0.0,
                "source": "ocr",
                "word_count": sum(item["word_count"] for item in ocr_pages),
                "words": all_words,
                "psm": sorted({item["psm"] for item in ocr_pages}),
            }
            page_results.append(page_data)
            fields.append(_page_field(page_data, "ocr"))
        else:
            page_results.append({"page": page_number, "text": embedded, "confidence": 0.0, "source": "unreadable", "word_count": 0})

    text = _normalise_text("\n\n".join(item["text"] for item in page_results if item["text"]))[:MAX_TEXT_CHARS]
    return ExtractionResult(
        text=text,
        extractor="pypdf+tesseract-tsv" if used_ocr else "pypdf",
        language="+".join(sorted(languages)),
        quality_data={
            "pages": [{key: value for key, value in item.items() if key != "text"} for item in page_results],
            "used_ocr": used_ocr,
            "page_count": len(page_results),
        },
        fields=fields,
        needs_review=used_ocr or any(item["source"] == "unreadable" for item in page_results),
    )


def extract_document(document):
    try:
        handle = open_canonical(document.canonical_file)
    except (FileNotFoundError, OSError) as exc:
        raise ProcessingError("canonical_missing", "Die kanonische Dokumentdatei fehlt.") from exc
    try:
        if document.mime_type == "application/pdf":
            return _extract_pdf(handle)
        if document.mime_type.startswith("image/"):
            return _extract_image(handle)
        raise ProcessingError("unsupported_mime", "Der Dokumenttyp kann nicht lokal verarbeitet werden.")
    finally:
        handle.close()
