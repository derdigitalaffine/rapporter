import re


AVATAR_MODES = ("initials", "icon", "photo")
AVATAR_COLOR_PALETTE = (
    "#2F855A", "#2563EB", "#7C3AED", "#DB2777", "#C2410C", "#0F766E",
    "#B91C1C", "#4F46E5", "#A65353", "#8A7A32", "#357A68", "#626A73",
)

# Stable keys only. They map to a curated frontend avatar symbol registry; no
# arbitrary Font Awesome class names, SVG data or HTML strings are persisted.
AVATAR_ICON_KEYS = (
    "user", "heart", "favorite", "pet", "dog", "cat", "fish", "dragon", "baby",
    "home", "bed", "tree", "sun", "moon", "rainbow", "rocket", "football", "gamepad",
    "music", "cake", "gift", "car", "recycle", "utensils", "water", "broom", "weather",
    "frost", "rain", "bolt", "light", "school", "transit", "route", "location", "calendar",
    "clock", "tasks", "shopping", "store", "lists", "inbox", "members", "link", "share",
    "camera", "microphone", "play", "robot", "email", "receipt", "archive", "sliders",
    "priority", "tags", "trend", "hot", "progress", "automation", "integrations", "waste",
    "install", "settle", "euro", "send",
)

_HEX_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")


def deterministic_avatar_color(user_id):
    try:
        value = int(user_id)
    except (TypeError, ValueError):
        value = sum(ord(char) for char in str(user_id or "0"))
    return AVATAR_COLOR_PALETTE[value % len(AVATAR_COLOR_PALETTE)]


def normalize_avatar_color(value):
    color = str(value or "").strip()
    if not _HEX_COLOR.fullmatch(color):
        raise ValueError("Avatarfarbe muss eine gültige Hex-Farbe sein.")
    return color.upper()


def normalize_avatar_mode(value):
    mode = str(value or "").strip().lower()
    if mode not in AVATAR_MODES:
        raise ValueError("Ungültige Avatar-Darstellung.")
    return mode


def normalize_avatar_icon(value):
    key = str(value or "").strip()
    if key not in AVATAR_ICON_KEYS:
        raise ValueError("Dieses Avatar-Symbol ist nicht verfügbar.")
    return key


def ensure_avatar_color(profile, preferred_color=None):
    stored = str(getattr(profile, "avatar_color", "") or "").strip()
    if _HEX_COLOR.fullmatch(stored):
        return stored.upper()
    preferred = str(preferred_color or "").strip()
    color = preferred.upper() if _HEX_COLOR.fullmatch(preferred) else deterministic_avatar_color(profile.user_id)
    profile.avatar_color = color
    profile.save(update_fields=["avatar_color", "updated_at"])
    return color


def avatar_color(profile):
    stored = str(getattr(profile, "avatar_color", "") or "").strip()
    return stored.upper() if _HEX_COLOR.fullmatch(stored) else deterministic_avatar_color(profile.user_id)


def avatar_mode(profile):
    mode = str(getattr(profile, "avatar_mode", "") or "").strip()
    if mode == "photo" and not profile.avatar_key:
        return "icon" if getattr(profile, "avatar_icon_key", "") else "initials"
    if mode == "icon" and not getattr(profile, "avatar_icon_key", ""):
        return "initials"
    if mode in AVATAR_MODES:
        return mode
    if profile.avatar_key:
        return "photo"
    return "icon" if getattr(profile, "avatar_icon_key", "") else "initials"


def appearance_payload(profile, preferred_color=None):
    return {
        "avatar_mode": avatar_mode(profile),
        "avatar_icon_key": getattr(profile, "avatar_icon_key", "") or "",
        "avatar_color": ensure_avatar_color(profile, preferred_color),
        "avatar_color_palette": list(AVATAR_COLOR_PALETTE),
        "avatar_icon_options": list(AVATAR_ICON_KEYS),
    }
