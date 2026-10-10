"""Non-destructive local image quality assessment for document OCR."""
import io
from math import sqrt

from PIL import Image, ImageFilter, ImageOps, ImageStat

MAX_SKEW_SAMPLE_DIMENSION = 480
SKEW_CANDIDATES = (-3.0, -2.0, -1.0, 0.0, 1.0, 2.0, 3.0)


def assess_image(image):
    """Return bounded, content-agnostic quality signals for operator/review UX."""
    gray = ImageOps.grayscale(image)
    stat = ImageStat.Stat(gray)
    brightness = float(stat.mean[0])
    contrast = sqrt(max(0.0, float(stat.var[0])))
    edges = gray.filter(ImageFilter.FIND_EDGES)
    edge_stat = ImageStat.Stat(edges)
    sharpness = sqrt(max(0.0, float(edge_stat.var[0])))
    warnings = []
    if min(gray.size) < 700:
        warnings.append("low_resolution")
    if brightness < 55:
        warnings.append("dark")
    elif brightness > 245:
        warnings.append("overexposed")
    if sharpness < 8:
        warnings.append("possibly_blurry")
    return {
        "width": gray.width,
        "height": gray.height,
        "megapixels": round((gray.width * gray.height) / 1_000_000, 3),
        "brightness": round(brightness, 2),
        "contrast": round(contrast, 2),
        "sharpness": round(sharpness, 2),
        "warnings": warnings,
    }


def assess_canonical_image(canonical):
    """Assess already-validated canonical image bytes without domain duplication."""
    if not canonical.mime_type.startswith("image/"):
        return {"warnings": []}
    with Image.open(io.BytesIO(canonical.content)) as image:
        image.load()
        return assess_image(image)


def _projection_score(binary):
    width, height = binary.size
    pixels = binary.load()
    previous = 0
    score = 0
    for y in range(height):
        ink = 0
        for x in range(width):
            if pixels[x, y] < 128:
                ink += 1
        delta = ink - previous
        score += delta * delta
        previous = ink
    return score


def estimate_skew(image):
    """Estimate only small page skew; large rotations belong to EXIF/capture handling.

    A bounded downscaled high-contrast copy is scored by horizontal text-line
    projection. The canonical file is never changed; the selected angle applies
    only to the transient OCR image.
    """
    gray = ImageOps.grayscale(image)
    sample = gray.copy()
    sample.thumbnail((MAX_SKEW_SAMPLE_DIMENSION, MAX_SKEW_SAMPLE_DIMENSION), Image.Resampling.LANCZOS)
    sample = ImageOps.autocontrast(sample)
    threshold = int(ImageStat.Stat(sample).mean[0])
    binary = sample.point(lambda value: 0 if value < threshold else 255, mode="1").convert("L")
    scores = {}
    for angle in SKEW_CANDIDATES:
        candidate = binary if angle == 0 else binary.rotate(
            angle,
            resample=Image.Resampling.BILINEAR,
            expand=False,
            fillcolor=255,
        )
        scores[angle] = _projection_score(candidate)
    baseline = scores[0.0]
    best_angle = max(scores, key=scores.get)
    # Avoid rotating for noise or marginal gains. This is intentionally
    # conservative because OCR preprocessing must not be destructive.
    if best_angle == 0.0 or baseline <= 0 or scores[best_angle] < baseline * 1.08:
        return 0.0
    return float(best_angle)


def prepare_for_ocr(image):
    """Build a transient OCR view plus quality/preprocessing metadata."""
    oriented = ImageOps.exif_transpose(image).convert("RGB")
    quality = assess_image(oriented)
    gray = ImageOps.grayscale(oriented)
    angle = estimate_skew(gray)
    if angle:
        gray = gray.rotate(angle, resample=Image.Resampling.BICUBIC, expand=True, fillcolor=255)
    gray = ImageOps.autocontrast(gray, cutoff=1)
    quality["preprocessing"] = {
        "exif_transposed": True,
        "deskew_degrees": angle,
        "contrast": "autocontrast-1pct",
        "destructive_thresholding": False,
    }
    return gray, quality
