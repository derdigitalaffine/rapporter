from dataclasses import dataclass


@dataclass(frozen=True)
class CapabilitySpec:
    key: str
    domain: str
    description: str
    default_light: bool = False
    premium: bool = False


CAPABILITY_SPECS = (
    CapabilitySpec("family_management", "family", "Familien- und Mitgliederverwaltung", default_light=True),
    CapabilitySpec("calendar", "calendar", "Gemeinsamer Familienkalender", default_light=True),
    CapabilitySpec("todo", "todo", "Basis-Aufgaben und Routinen", default_light=True),
    CapabilitySpec("shopping", "shopping", "Gemeinsame Einkaufslisten", default_light=True),
    CapabilitySpec("pinboard", "pinboard", "Universelle Familien-Pinnwand", default_light=True),
    CapabilitySpec("notes", "notes", "Einfache Familiennotizen", default_light=True),
    CapabilitySpec("travel", "travel", "Reiseplanung und Travel Hub", premium=True),
    CapabilitySpec("documents", "documents", "Document Core und Dokument-Workflows", premium=True),
    CapabilitySpec("school", "school", "Schule und Lernintegrationen", premium=True),
    CapabilitySpec("children", "children", "Kinder- und Vorsorge-Power-Features", premium=True),
    CapabilitySpec("pregnancy_baby", "baby", "Schwangerschaft und Baby-Power-Features", premium=True),
    CapabilitySpec("pets", "pets", "Haustier-Power-Features", premium=True),
    CapabilitySpec("advanced_integrations", "integrations", "Erweiterte Integrationen", premium=True),
    CapabilitySpec("advanced_tasks", "todo", "Erweiterte Task-/Workflow-Funktionen", premium=True),
)

CAPABILITY_KEYS = frozenset(spec.key for spec in CAPABILITY_SPECS)
LIGHT_CAPABILITY_KEYS = frozenset(spec.key for spec in CAPABILITY_SPECS if spec.default_light)
PREMIUM_CAPABILITY_KEYS = frozenset(spec.key for spec in CAPABILITY_SPECS if spec.premium)
FULL_ACCESS_PLAN_KEYS = frozenset({"premium", "vip"})
VALID_PLAN_KEYS = frozenset({"light", *FULL_ACCESS_PLAN_KEYS})
COMMERCIAL_CUTOVER_KEY = "commercial-v1"
LEGACY_SOURCE_REF = "commercial-cutover:legacy-vip-v1"
