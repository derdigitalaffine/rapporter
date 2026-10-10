from dataclasses import dataclass
import re


class TelemetrySchemaError(ValueError):
    pass


SAFE_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9_.:-]{0,63}$")
HEX_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")
REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{1,64}$")
OPAQUE_TARGET_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")

ACTOR_CLASSES = frozenset({"user", "superadmin", "system"})
OUTCOMES = frozenset({"success", "denied", "failed"})
REASON_CATEGORIES = frozenset(
    {
        "invalid_credentials",
        "inactive_account",
        "rate_limited",
        "policy_denied",
        "expired",
        "revoked",
        "user_request",
        "admin_action",
        "system",
        "unknown",
    }
)
TARGET_TYPES = frozenset(
    {
        "user",
        "family",
        "membership",
        "invite",
        "session",
        "passkey",
        "config",
        "export",
        "entitlement",
        "mail",
        "push",
    }
)
MODULE_KEYS = frozenset(
    {
        "tasks",
        "shopping",
        "calendar",
        "routines",
        "notes",
        "board",
        "travel",
        "documents",
        "baby",
        "pets",
        "expenses",
        "integrations",
        "notifications",
    }
)


@dataclass(frozen=True)
class AuditSpec:
    metadata_keys: frozenset[str] = frozenset()


AUDIT_EVENT_SPECS = {
    "auth.login.succeeded": AuditSpec(frozenset({"auth_method"})),
    "auth.login.failed": AuditSpec(frozenset({"auth_method", "identifier_hash"})),
    "auth.rate_limited": AuditSpec(frozenset({"scope", "identifier_hash"})),
    "auth.logout": AuditSpec(),
    "auth.password_reset.completed": AuditSpec(),
    "auth.email.verified": AuditSpec(),
    "auth.passkey.registered": AuditSpec(),
    "auth.passkey.removed": AuditSpec(),
    "auth.session.revoked": AuditSpec(frozenset({"auth_method"})),
    "family.created": AuditSpec(),
    "membership.joined": AuditSpec(frozenset({"role"})),
    "membership.removed": AuditSpec(frozenset({"role"})),
    "membership.role_changed": AuditSpec(frozenset({"role"})),
    "invite.created": AuditSpec(frozenset({"role"})),
    "invite.sent": AuditSpec(frozenset({"role"})),
    "invite.accepted": AuditSpec(frozenset({"role"})),
    "invite.expired": AuditSpec(),
    "invite.revoked": AuditSpec(),
    "superadmin.family.suspended": AuditSpec(),
    "superadmin.family.reactivated": AuditSpec(),
    "superadmin.export.created": AuditSpec(frozenset({"export_kind"})),
    "entitlement.granted": AuditSpec(frozenset({"origin"})),
    "entitlement.revoked": AuditSpec(frozenset({"origin"})),
    "mail.sent": AuditSpec(),
    "mail.failed": AuditSpec(frozenset({"error_class"})),
    "push.sent": AuditSpec(),
    "push.failed": AuditSpec(frozenset({"error_class"})),
}

USAGE_EVENT_KEYS = frozenset({"activity.foreground", "module.used"})


def _safe_slug(value, *, field):
    text = str(value or "")
    if not SAFE_SLUG_RE.fullmatch(text):
        raise TelemetrySchemaError(f"invalid_{field}")
    return text


def validate_request_id(value):
    if value in (None, ""):
        return ""
    text = str(value)
    if not REQUEST_ID_RE.fullmatch(text):
        raise TelemetrySchemaError("invalid_request_id")
    return text


def validate_reason(value):
    if value in (None, ""):
        return ""
    text = str(value)
    if text not in REASON_CATEGORIES:
        raise TelemetrySchemaError("invalid_reason")
    return text


def validate_target(target_type, target_id):
    if not target_type and not target_id:
        return "", ""
    target_type = str(target_type or "")
    target_id = str(target_id or "")
    if target_type not in TARGET_TYPES or not OPAQUE_TARGET_RE.fullmatch(target_id):
        raise TelemetrySchemaError("invalid_target")
    return target_type, target_id


def _validate_metadata_value(key, value):
    if key == "auth_method":
        if value not in {"password", "passkey", "legacy"}:
            raise TelemetrySchemaError("invalid_metadata_auth_method")
        return value
    if key == "identifier_hash":
        text = str(value or "")
        if not HEX_DIGEST_RE.fullmatch(text):
            raise TelemetrySchemaError("invalid_metadata_identifier_hash")
        return text
    if key == "role":
        if value not in {"owner", "adult", "teen", "child", "guest"}:
            raise TelemetrySchemaError("invalid_metadata_role")
        return value
    if key in {"scope", "export_kind", "origin", "error_class"}:
        return _safe_slug(value, field=f"metadata_{key}")
    raise TelemetrySchemaError("unknown_metadata_key")


def validate_audit_event(event_key, *, actor_class, outcome, reason="", metadata=None, request_id="", target_type="", target_id=""):
    try:
        spec = AUDIT_EVENT_SPECS[str(event_key)]
    except KeyError as exc:
        raise TelemetrySchemaError("unknown_audit_event") from exc
    if actor_class not in ACTOR_CLASSES:
        raise TelemetrySchemaError("invalid_actor_class")
    if outcome not in OUTCOMES:
        raise TelemetrySchemaError("invalid_outcome")
    clean_metadata = {}
    supplied = metadata or {}
    if not isinstance(supplied, dict):
        raise TelemetrySchemaError("invalid_metadata")
    unknown = set(supplied) - set(spec.metadata_keys)
    if unknown:
        raise TelemetrySchemaError("unknown_metadata_key")
    for key, value in supplied.items():
        clean_metadata[key] = _validate_metadata_value(key, value)
    target_type, target_id = validate_target(target_type, target_id)
    return {
        "event_key": str(event_key),
        "actor_class": actor_class,
        "outcome": outcome,
        "reason": validate_reason(reason),
        "metadata": clean_metadata,
        "request_id": validate_request_id(request_id),
        "target_type": target_type,
        "target_id": target_id,
    }


def validate_usage_event(event_key, dimension_key=""):
    event_key = str(event_key)
    if event_key not in USAGE_EVENT_KEYS:
        raise TelemetrySchemaError("unknown_usage_event")
    if event_key == "module.used":
        if dimension_key not in MODULE_KEYS:
            raise TelemetrySchemaError("invalid_module_key")
        return event_key, dimension_key
    if dimension_key:
        raise TelemetrySchemaError("unexpected_usage_dimension")
    return event_key, ""
