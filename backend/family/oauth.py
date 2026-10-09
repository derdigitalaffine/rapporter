import os
from datetime import datetime, timedelta
from urllib.parse import urlencode

import requests
from django.core import signing
from django.utils import timezone

from .models import Family, IntegrationSource

GOOGLE_AUTHORIZE = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN = "https://oauth2.googleapis.com/token"
MICROSOFT_AUTHORIZE = "https://login.microsoftonline.com/common/oauth2/v2.0/authorize"
MICROSOFT_TOKEN = "https://login.microsoftonline.com/common/oauth2/v2.0/token"
STATE_SALT = "fam-uh-le-calendar-oauth-v1"


def _credentials(provider):
    prefix = "GOOGLE" if provider == "google" else "MICROSOFT"
    client_id = os.getenv(f"{prefix}_OAUTH_CLIENT_ID", "").strip()
    client_secret = os.getenv(f"{prefix}_OAUTH_CLIENT_SECRET", "").strip()
    if not client_id or not client_secret:
        raise ValueError(f"{provider.title()} OAuth ist im Setup noch nicht konfiguriert.")
    return client_id, client_secret


def oauth_available(provider):
    try:
        _credentials(provider)
        return True
    except ValueError:
        return False


def authorization_url(provider, family, user, redirect_uri):
    if provider not in {"google", "microsoft"}:
        raise ValueError("Unbekannter OAuth-Anbieter.")
    client_id, _ = _credentials(provider)
    state = signing.dumps(
        {"provider": provider, "family": str(family.id), "user": user.pk},
        salt=STATE_SALT,
        compress=True,
    )
    if provider == "google":
        params = {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": "https://www.googleapis.com/auth/calendar.readonly",
            "access_type": "offline",
            "prompt": "consent",
            "include_granted_scopes": "true",
            "state": state,
        }
        return f"{GOOGLE_AUTHORIZE}?{urlencode(params)}"
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "response_mode": "query",
        "scope": "offline_access Calendars.Read",
        "state": state,
    }
    return f"{MICROSOFT_AUTHORIZE}?{urlencode(params)}"


def _post_token(url, data):
    response = requests.post(url, data=data, timeout=15, headers={"User-Agent": "fam-uh-le/1.0"})
    response.raise_for_status()
    payload = response.json()
    if payload.get("error"):
        raise ValueError(payload.get("error_description") or payload["error"])
    return payload


def complete_oauth(code, state, redirect_uri):
    try:
        state_data = signing.loads(state, salt=STATE_SALT, max_age=600)
    except signing.BadSignature as exc:
        raise ValueError("OAuth-Status ist ungültig oder abgelaufen.") from exc
    provider = state_data.get("provider")
    family = Family.objects.filter(id=state_data.get("family"), memberships__user_id=state_data.get("user")).first()
    if not family or provider not in {"google", "microsoft"}:
        raise ValueError("OAuth-Zuordnung ist ungültig.")
    client_id, client_secret = _credentials(provider)
    if provider == "google":
        tokens = _post_token(GOOGLE_TOKEN, {
            "code": code,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        })
        name, adapter = "Google Kalender", "google_oauth"
    else:
        tokens = _post_token(MICROSOFT_TOKEN, {
            "code": code,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
            "scope": "offline_access Calendars.Read",
        })
        name, adapter = "Microsoft Outlook Kalender", "microsoft_oauth"
    config = {
        "adapter": adapter,
        "oauth_provider": provider,
        "access_token": tokens.get("access_token", ""),
        "refresh_token": tokens.get("refresh_token", ""),
        "expires_at": (timezone.now() + timedelta(seconds=max(60, int(tokens.get("expires_in", 3600)) - 60))).isoformat(),
    }
    source = IntegrationSource.objects.filter(family=family, config__adapter=adapter).first()
    if source:
        source.name = name
        source.kind = IntegrationSource.Kind.ICS
        source.endpoint = ""
        source.config = config
        source.enabled = True
        source.save()
    else:
        source = IntegrationSource.objects.create(
            family=family,
            kind=IntegrationSource.Kind.ICS,
            name=name,
            endpoint="",
            config=config,
            enabled=True,
        )
    return source, provider


def refresh_access_token(source, provider):
    cfg = dict(source.config or {})
    access_token = cfg.get("access_token", "")
    expires_at = cfg.get("expires_at")
    if access_token and expires_at:
        try:
            expiry = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
            if timezone.is_naive(expiry):
                expiry = timezone.make_aware(expiry)
            if expiry > timezone.now() + timedelta(minutes=2):
                return access_token
        except (TypeError, ValueError):
            pass
    refresh_token = cfg.get("refresh_token")
    if not refresh_token:
        raise ValueError("OAuth-Aktualisierung erforderlich. Bitte Kalender neu verbinden.")
    client_id, client_secret = _credentials(provider)
    if provider == "google":
        tokens = _post_token(GOOGLE_TOKEN, {
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        })
    else:
        tokens = _post_token(MICROSOFT_TOKEN, {
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
            "scope": "offline_access Calendars.Read",
        })
    cfg["access_token"] = tokens.get("access_token", access_token)
    cfg["refresh_token"] = tokens.get("refresh_token", refresh_token)
    cfg["expires_at"] = (timezone.now() + timedelta(seconds=max(60, int(tokens.get("expires_in", 3600)) - 60))).isoformat()
    source.config = cfg
    source.save(update_fields=["config", "updated_at"])
    return cfg["access_token"]
