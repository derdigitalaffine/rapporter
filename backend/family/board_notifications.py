from .domain_notifications import EVENT_SPECS
from .notification_digests import IMPORTANT

EVENT_SPECS.setdefault(
    "board.created",
    {
        "pref": "messages",
        "title": {"de": "Neuer Beitrag am Schwarzen Brett", "en": "New family board post"},
        "body": {"de": "{actor} hat einen Familienbeitrag veröffentlicht.", "en": "{actor} published a family post."},
    },
)

# Interaction copy stays generic: source titles and comment bodies can be more
# sensitive than the Pin shell and must never leak through notifications.
EVENT_SPECS.setdefault(
    "pin.comment",
    {
        "pref": "messages",
        "title": {"de": "Neue Pinnwand-Aktivität", "en": "New pinboard activity"},
        "body": {"de": "{actor} hat auf der Pinnwand kommentiert.", "en": "{actor} commented on the pinboard."},
    },
)
EVENT_SPECS.setdefault(
    "pin.mention",
    {
        "pref": "messages",
        "title": {"de": "Du wurdest auf der Pinnwand erwähnt", "en": "You were mentioned on the pinboard"},
        "body": {"de": "{actor} hat dich in einer Pinnwand-Aktivität erwähnt.", "en": "{actor} mentioned you in pinboard activity."},
    },
)
EVENT_SPECS.setdefault(
    "pin.reaction",
    {
        "pref": "messages",
        "title": {"de": "Reaktion auf der Pinnwand", "en": "Pinboard reaction"},
        "body": {"de": "Neue Aktivität auf der Pinnwand.", "en": "New activity on the pinboard."},
    },
)

# A direct mention remains important even when a user selected the compact
# notification level. Reactions themselves are recorded in-app only.
IMPORTANT.add("pin.mention")
