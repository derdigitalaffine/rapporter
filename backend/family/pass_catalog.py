"""Fixed, server-authoritative pass icon registry.

Keys and glyphs are data, never CSS/HTML class names.  This keeps pass branding useful
without turning persisted values into an injection surface.
"""

PASS_ICON_ROWS = (
    ("card", "general", "Karte", "Card", "▣", "#6750A4"),
    ("star", "general", "Favorit", "Favorite", "★", "#7B61A8"),
    ("gift", "general", "Geschenk", "Gift", "🎁", "#A43D73"),
    ("heart", "general", "Herz", "Heart", "♥", "#B3261E"),
    ("crown", "general", "Krone", "Crown", "♛", "#8A6400"),
    ("diamond", "general", "Diamant", "Diamond", "◆", "#006A6A"),
    ("key", "general", "Schlüssel", "Key", "🔑", "#6B5E00"),
    ("wallet", "general", "Wallet", "Wallet", "▤", "#4F6354"),
    ("shop", "shopping", "Geschäft", "Shop", "🏬", "#005AC1"),
    ("cart", "shopping", "Einkaufswagen", "Cart", "🛒", "#386A20"),
    ("bag", "shopping", "Einkaufstasche", "Shopping bag", "🛍", "#8F4C38"),
    ("tag", "shopping", "Preisschild", "Tag", "🏷", "#725188"),
    ("percent", "shopping", "Rabatt", "Discount", "%", "#8C5000"),
    ("coupon", "shopping", "Coupon", "Coupon", "✂", "#984061"),
    ("grocery", "shopping", "Supermarkt", "Grocery", "🥕", "#386A20"),
    ("pharmacy", "shopping", "Apotheke", "Pharmacy", "⚕", "#006A60"),
    ("coffee", "food", "Café", "Coffee", "☕", "#7C5635"),
    ("food", "food", "Essen", "Food", "🍴", "#805610"),
    ("restaurant", "food", "Restaurant", "Restaurant", "🍽", "#934173"),
    ("ticket", "events", "Ticket", "Ticket", "🎟", "#6750A4"),
    ("event", "events", "Veranstaltung", "Event", "◫", "#625B71"),
    ("concert", "events", "Konzert", "Concert", "♫", "#9C4146"),
    ("cinema", "events", "Kino", "Cinema", "🎬", "#5E5E7D"),
    ("theater", "events", "Theater", "Theatre", "🎭", "#7A5265"),
    ("museum", "events", "Museum", "Museum", "🏛", "#56633F"),
    ("sports", "events", "Sport", "Sports", "⚽", "#386A20"),
    ("stadium", "events", "Stadion", "Stadium", "🏟", "#006A6A"),
    ("plane", "travel", "Flug", "Flight", "✈", "#0061A4"),
    ("boarding", "travel", "Boardingpass", "Boarding pass", "✈", "#3F51B5"),
    ("train", "travel", "Zug", "Train", "🚆", "#455A64"),
    ("bus", "travel", "Bus", "Bus", "🚌", "#006874"),
    ("tram", "travel", "Straßenbahn", "Tram", "🚋", "#006C4C"),
    ("subway", "travel", "U-Bahn", "Subway", "Ⓜ", "#514700"),
    ("transit", "travel", "Nahverkehr", "Transit", "↔", "#00639B"),
    ("ship", "travel", "Schiff", "Ship", "⚓", "#00658A"),
    ("bike", "travel", "Fahrrad", "Bike", "🚲", "#386A20"),
    ("car", "travel", "Auto", "Car", "🚗", "#555F71"),
    ("parking", "travel", "Parken", "Parking", "Ⓟ", "#415F91"),
    ("fuel", "travel", "Tanken", "Fuel", "⛽", "#7A5900"),
    ("hotel", "travel", "Hotel", "Hotel", "🛏", "#725188"),
    ("fitness", "leisure", "Fitness", "Fitness", "🏋", "#8C5000"),
    ("pool", "leisure", "Schwimmbad", "Pool", "🏊", "#00658A"),
    ("game", "leisure", "Gaming", "Gaming", "🎮", "#6750A4"),
    ("music", "leisure", "Musik", "Music", "♪", "#984061"),
    ("book", "leisure", "Buch", "Book", "📖", "#4F6354"),
    ("camera", "leisure", "Kamera", "Camera", "📷", "#5F5E62"),
    ("library", "membership", "Bibliothek", "Library", "▥", "#52634F"),
    ("school", "membership", "Schule", "School", "🎓", "#415F91"),
    ("university", "membership", "Hochschule", "University", "🏫", "#4A4458"),
    ("work", "membership", "Arbeit", "Work", "💼", "#545F70"),
    ("club", "membership", "Verein", "Club", "♣", "#386A20"),
    ("family", "membership", "Familie", "Family", "👪", "#8F4C38"),
    ("child", "membership", "Kind", "Child", "●", "#7D5260"),
    ("pet", "membership", "Tier", "Pet", "🐾", "#685F12"),
    ("health", "services", "Gesundheit", "Health", "+", "#006A60"),
    ("insurance", "services", "Versicherung", "Insurance", "◆", "#415F91"),
    ("bank", "services", "Bank", "Bank", "▥", "#4A5F2A"),
    ("phone", "services", "Mobilfunk", "Mobile", "☎", "#006874"),
    ("wifi", "services", "WLAN", "Wi-Fi", "⌁", "#00639B"),
    ("cloud", "services", "Cloud", "Cloud", "☁", "#5B5F71"),
    ("home", "services", "Zuhause", "Home", "⌂", "#7C5800"),
    ("leaf", "services", "Nachhaltigkeit", "Sustainability", "❧", "#386A20"),
    ("recycle", "services", "Recycling", "Recycling", "♻", "#006C4C"),
)

PASS_ICON_INDEX = {
    key: {
        "key": key,
        "group": group,
        "label_de": label_de,
        "label_en": label_en,
        "glyph": glyph,
        "accent": accent,
    }
    for key, group, label_de, label_en, glyph, accent in PASS_ICON_ROWS
}
PASS_ICON_KEYS = frozenset(PASS_ICON_INDEX)


def pass_icon_catalog():
    return list(PASS_ICON_INDEX.values())


def auto_accent(icon_key, fallback="#6750A4"):
    row = PASS_ICON_INDEX.get(icon_key or "")
    return row["accent"] if row else fallback
