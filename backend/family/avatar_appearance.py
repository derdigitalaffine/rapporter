import re


AVATAR_MODES = ("initials", "icon", "photo")
AVATAR_COLOR_PALETTE = (
    "#2F6F73", "#3F6FA8", "#6B5FA7", "#8A5E8D",
    "#A65353", "#A86E35", "#8A7A32", "#4F7B45",
    "#357A68", "#426E8A", "#755B45", "#626A73",
)

# Stable keys only. They map to the existing central frontend Icon registry; no
# arbitrary Font Awesome class names or SVG/HTML strings are persisted.
AVATAR_ICON_KEYS = (
    "user", "heart", "favorite", "pet", "dog", "baby", "home", "bed",
    "car", "recycle", "utensils", "water", "broom", "weather", "frost", "rain",
    "bolt", "light", "school", "transit", "route", "location", "calendar", "clock",
    "tasks", "shopping", "store", "lists", "inbox", "members", "link", "share",
    "camera", "microphone", "play", "music", "gift", "cake", "rocket", "football",
    "rainbow", "tree", "sun", "moon", "cat", "fish", "dragon", "gamepad",
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


def avatar_color(profile):
    stored = str(getattr(profile, "avatar_color", "") or "").strip()
    return stored if _HEX_COLOR.fullmatch(stored) else deterministic_avatar_color(profile.user_id)


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


def appearance_payload(profile):
    return {
        "avatar_mode": avatar_mode(profile),
        "avatar_icon_key": getattr(profile, "avatar_icon_key", "") or "",
        "avatar_color": avatar_color(profile),
        "avatar_color_palette": list(AVATAR_COLOR_PALETTE),
        "avatar_icon_options": list(AVATAR_ICON_KEYS),
    }
