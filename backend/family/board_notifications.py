from .domain_notifications import EVENT_SPECS

EVENT_SPECS.setdefault(
    "board.created",
    {
        "pref": "messages",
        "title": {"de": "Neuer Beitrag am Schwarzen Brett", "en": "New family board post"},
        "body": {"de": "{actor} hat einen Familienbeitrag veröffentlicht.", "en": "{actor} published a family post."},
    },
)
