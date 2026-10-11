from urllib.parse import urlparse

from django.conf import settings
from django.core.checks import Error, register


@register()
def check_webauthn_configuration(app_configs, **kwargs):
    if not getattr(settings, "WEBAUTHN_ENABLED", False):
        return []

    origin = (getattr(settings, "WEBAUTHN_ORIGIN", "") or getattr(settings, "APP_URL", "")).strip().rstrip("/")
    rp_id = getattr(settings, "WEBAUTHN_RP_ID", "").strip()
    errors = []
    if not origin:
        return [
            Error(
                "WEBAUTHN_ENABLED requires WEBAUTHN_ORIGIN or APP_URL.",
                id="auth_passkeys.E001",
            )
        ]

    parsed = urlparse(origin)
    host = (parsed.hostname or "").lower()
    if parsed.scheme not in {"https", "http"} or not host or parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
        errors.append(
            Error(
                "WebAuthn origin must be a bare http(s) origin without path, query, or fragment.",
                id="auth_passkeys.E002",
            )
        )
        return errors

    if parsed.scheme != "https" and host not in {"localhost", "127.0.0.1", "::1"}:
        errors.append(
            Error(
                "WebAuthn requires HTTPS outside localhost development.",
                id="auth_passkeys.E003",
            )
        )

    effective_rp_id = (rp_id or host).lower().strip(".")
    if not effective_rp_id or "*" in effective_rp_id:
        errors.append(
            Error(
                "WEBAUTHN_RP_ID must be an explicit host/domain and may not contain wildcards.",
                id="auth_passkeys.E004",
            )
        )
    elif host != effective_rp_id and not host.endswith("." + effective_rp_id):
        errors.append(
            Error(
                "WEBAUTHN_RP_ID must equal the origin host or be a registrable parent domain of it.",
                id="auth_passkeys.E005",
            )
        )
    return errors
