import re
import unicodedata

from django.db.models.signals import pre_save
from django.dispatch import receiver

from .models import FamilyEvent


WASTE_KIND_RULES = {
    "rest": (
        "restmuell",
        "restmull",
        "restabfall",
        "restafall",
        "hausmuell",
        "hausmull",
        "graue tonne",
        "grauer behalter",
        "grauer behaelter",
        "schwarze tonne",
        "residual waste",
    ),
    "yellow": (
        "gelbe tonne",
        "gelber sack",
        "gelbe sacke",
        "gelbe saecke",
        "leichtverpack",
        "verpackungsabfall",
        "wertstoff",
        "lvp",
        "yellow bin",
    ),
    "bio": (
        "biomuell",
        "biomull",
        "bioabfall",
        "biotonne",
        "braune tonne",
        "kompost",
        "organic waste",
    ),
    "paper": (
        "altpapier",
        "papiertonne",
        "blaue tonne",
        "papier",
        "pappe",
        "karton",
        "paper",
    ),
}


def normalize_waste_text(value):
    text = str(value or "").lower()
    text = text.replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")
    text = unicodedata.normalize("NFKD", text)
    text = "".join(char for char in text if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def detect_waste_kind(title, description=""):
    """Return a semantic waste kind from human calendar text.

    Exact/common municipal wording wins. If multiple fractions are mentioned,
    the fraction named first is used as the icon colour while all matches are
    retained separately by ``detect_waste_kinds``.
    """
    text = normalize_waste_text(f"{title or ''} {description or ''}")
    matches = []
    for kind, phrases in WASTE_KIND_RULES.items():
        positions = [text.find(phrase) for phrase in phrases if phrase in text]
        if positions:
            matches.append((min(positions), kind))
    return min(matches)[1] if matches else "unknown"


def detect_waste_kinds(title, description=""):
    text = normalize_waste_text(f"{title or ''} {description or ''}")
    matches = []
    for kind, phrases in WASTE_KIND_RULES.items():
        positions = [text.find(phrase) for phrase in phrases if phrase in text]
        if positions:
            matches.append((min(positions), kind))
    return [kind for _, kind in sorted(matches)]


@receiver(pre_save, sender=FamilyEvent)
def classify_waste_event(sender, instance, **kwargs):
    if not str(instance.type or "").startswith("waste."):
        return
    payload = dict(instance.payload or {})
    kinds = detect_waste_kinds(instance.title, payload.get("description", ""))
    payload["waste_kinds"] = kinds
    payload["waste_kind"] = kinds[0] if kinds else "unknown"
    instance.payload = payload
