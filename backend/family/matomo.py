import json
import re
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen

from django.conf import settings


class MatomoError(RuntimeError):
    pass


@dataclass(frozen=True)
class MatomoConfig:
    base_url: str
    site_id: str
    auth_token: str
    timeout: float

    @property
    def configured(self):
        return bool(self.base_url and self.site_id and self.auth_token)


def get_matomo_config():
    return MatomoConfig(
        base_url=str(getattr(settings, "MATOMO_BASE_URL", "") or "").strip().rstrip("/"),
        site_id=str(getattr(settings, "MATOMO_SITE_ID", "") or "").strip(),
        auth_token=str(getattr(settings, "MATOMO_AUTH_TOKEN", "") or "").strip(),
        timeout=float(getattr(settings, "MATOMO_API_TIMEOUT", 8) or 8),
    )


def public_matomo_config():
    config = get_matomo_config()
    return {
        "configured": config.configured,
        "site_id": config.site_id if config.configured else "",
    }


def _validated_api_url(config):
    parsed = urlsplit(config.base_url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise MatomoError("Matomo muss über eine gültige HTTPS-URL konfiguriert sein.")
    if parsed.query or parsed.fragment:
        raise MatomoError("Matomo Basis-URL darf keine Query oder Fragment-Komponente enthalten.")
    return f"{config.base_url}/index.php"


def _api_call(method, *, period="day", date="today", filter_limit=None, extra=None):
    config = get_matomo_config()
    if not config.configured:
        raise MatomoError("Matomo ist nicht vollständig konfiguriert.")

    params = {
        "module": "API",
        "method": method,
        "idSite": config.site_id,
        "period": period,
        "date": date,
        "format": "JSON",
        "token_auth": config.auth_token,
    }
    if filter_limit is not None:
        params["filter_limit"] = str(filter_limit)
    if extra:
        params.update({key: value for key, value in extra.items() if value is not None})

    request = Request(
        _validated_api_url(config),
        data=urlencode(params).encode("utf-8"),
        headers={"Content-Type": "application/x-www-form-urlencoded", "User-Agent": "FamilyOS-Matomo/1.0"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=config.timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        raise MatomoError(f"Matomo HTTP-Fehler {exc.code}.") from exc
    except (URLError, TimeoutError) as exc:
        raise MatomoError("Matomo ist derzeit nicht erreichbar.") from exc
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise MatomoError("Matomo hat keine gültige JSON-Antwort geliefert.") from exc

    if isinstance(payload, dict) and payload.get("result") == "error":
        # Matomo error payloads are external/untrusted data. Do not reflect their
        # message into the Superadmin API because it may contain configuration or
        # request details that do not belong in the browser-facing contract.
        raise MatomoError("Matomo Reporting API Fehler.")
    return payload


def _safe_page_label(value):
    text = str(value or "").strip()
    text = text.split("?", 1)[0].split("#", 1)[0]
    return text[:240]


_SUMMARY_FIELDS = (
    "nb_visits",
    "nb_uniq_visitors",
    "nb_actions",
    "nb_actions_per_visit",
    "avg_time_on_site",
    "bounce_rate",
)
_SERIES_FIELDS = ("nb_visits", "nb_uniq_visitors", "nb_actions")
_DATE_KEY = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _bounded_metrics(raw, *, fields):
    if not isinstance(raw, dict):
        return {}
    return {field: raw[field] for field in fields if field in raw}


def _bounded_series(raw):
    if not isinstance(raw, dict):
        return {}
    result = {}
    for day, metrics in raw.items():
        day = str(day)
        if not _DATE_KEY.fullmatch(day):
            continue
        result[day] = _bounded_metrics(metrics, fields=_SERIES_FIELDS)
    return result


def _bounded_rows(rows, *, kind):
    if not isinstance(rows, list):
        return []
    result = []
    for raw in rows:
        if not isinstance(raw, dict):
            continue
        if kind == "page":
            result.append({
                "label": _safe_page_label(raw.get("label")),
                "nb_visits": raw.get("nb_visits", 0),
                "nb_hits": raw.get("nb_hits", 0),
                "bounce_rate": raw.get("bounce_rate", ""),
                "avg_time_on_page": raw.get("avg_time_on_page", 0),
            })
        elif kind == "referrer":
            result.append({
                "label": str(raw.get("label") or "")[:120],
                "nb_visits": raw.get("nb_visits", 0),
                "nb_actions": raw.get("nb_actions", 0),
            })
        elif kind == "event":
            result.append({
                "label": str(raw.get("label") or "")[:120],
                "nb_visits": raw.get("nb_visits", 0),
                "nb_events": raw.get("nb_events", 0),
                "nb_events_with_value": raw.get("nb_events_with_value", 0),
            })
    return result


def reporting_snapshot(*, date_range):
    """Return a bounded, aggregate analytics snapshot for Superadmin.

    No raw visits, visitor IDs, IP addresses, URL query strings, arbitrary
    dimensions, or unbounded Matomo rows cross this integration boundary.
    """
    top_pages = _api_call(
        "Actions.getPageUrls",
        period="range",
        date=date_range,
        filter_limit=12,
        extra={"flat": "1", "showColumns": "label,nb_visits,nb_hits,bounce_rate,avg_time_on_page"},
    )
    referrers = _api_call(
        "Referrers.getReferrerType",
        period="range",
        date=date_range,
        filter_limit=10,
    )
    events = _api_call(
        "Events.getCategory",
        period="range",
        date=date_range,
        filter_limit=20,
    )
    summary = _api_call("VisitsSummary.get", period="range", date=date_range)
    series = _api_call("VisitsSummary.get", period="day", date=date_range)
    return {
        "summary": _bounded_metrics(summary, fields=_SUMMARY_FIELDS),
        "series": _bounded_series(series),
        "top_pages": _bounded_rows(top_pages, kind="page"),
        "referrers": _bounded_rows(referrers, kind="referrer"),
        "events": _bounded_rows(events, kind="event"),
    }
