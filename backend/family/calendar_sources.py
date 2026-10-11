CALENDAR_PRESENTATION_ICONS = frozenset({
    "calendar",
    "members",
    "school",
    "transit",
    "weather",
    "waste",
    "warning",
})

CALENDAR_PRESENTATION_TONES = frozenset({
    "blue",
    "green",
    "violet",
    "orange",
    "red",
    "teal",
})

_PRESENTATION_KEY = "calendar_presentation"
_PRESENTATION_FIELDS = frozenset({"icon", "tone", "label"})


def _normalize_presentation(value, *, strict):
    if value in (None, {}):
        return {}
    if not isinstance(value, dict):
        if strict:
            raise ValueError("calendar_presentation must be an object.")
        return {}

    unknown = set(value) - _PRESENTATION_FIELDS
    if unknown and strict:
        raise ValueError(f"Unknown calendar_presentation fields: {', '.join(sorted(unknown))}.")

    result = {}
    icon = value.get("icon")
    if icon is not None:
        if not isinstance(icon, str) or icon not in CALENDAR_PRESENTATION_ICONS:
            if strict:
                raise ValueError("calendar_presentation.icon is not supported.")
        else:
            result["icon"] = icon

    tone = value.get("tone")
    if tone is not None:
        if not isinstance(tone, str) or tone not in CALENDAR_PRESENTATION_TONES:
            if strict:
                raise ValueError("calendar_presentation.tone is not supported.")
        else:
            result["tone"] = tone

    label = value.get("label")
    if label is not None:
        if not isinstance(label, str):
            if strict:
                raise ValueError("calendar_presentation.label must be text.")
        else:
            label = label.strip()
            if not label or len(label) > 80 or any(ord(char) < 32 for char in label):
                if strict:
                    raise ValueError("calendar_presentation.label must contain 1–80 printable characters.")
            else:
                result["label"] = label

    return result


def validate_calendar_source_config(config):
    """Return a copy with a normalized, allowlisted calendar presentation."""
    if config is None:
        return {}
    if not isinstance(config, dict):
        raise ValueError("config must be an object.")

    normalized = dict(config)
    if _PRESENTATION_KEY in normalized:
        presentation = _normalize_presentation(normalized.get(_PRESENTATION_KEY), strict=True)
        if presentation:
            normalized[_PRESENTATION_KEY] = presentation
        else:
            normalized.pop(_PRESENTATION_KEY, None)
    return normalized


def safe_calendar_source_metadata(source):
    """Expose only non-secret source identity and allowlisted presentation data."""
    if source is None:
        return None
    config = source.config if isinstance(source.config, dict) else {}
    presentation = _normalize_presentation(config.get(_PRESENTATION_KEY), strict=False)
    return {
        "id": str(source.id),
        "name": source.name,
        "kind": source.kind,
        "presentation": presentation,
    }
