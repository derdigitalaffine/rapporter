"""Register privacy-safe Pin interaction moderation telemetry."""

from telemetry import catalog

catalog.AUDIT_EVENT_SPECS.setdefault("pin.comment.moderated", catalog.AuditSpec())
if "pin_comment" not in catalog.TARGET_TYPES:
    catalog.TARGET_TYPES = frozenset((*catalog.TARGET_TYPES, "pin_comment"))
