import logging
import secrets
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit, urlunsplit
from urllib.request import Request, urlopen

from django.conf import settings

logger = logging.getLogger("telemetry")


class ProductAnalyticsError(RuntimeError):
    pass


class ProductAnalyticsSchemaError(ValueError):
    pass


PRODUCT_EVENT_VERSION = 1
PRODUCT_KINDS = frozenset({"pageview", "event"})
PRODUCT_FEATURES = frozenset(
    {
        "home",
        "tasks",
        "shopping",
        "calendar",
        "routines",
        "notes",
        "board",
        "travel",
        "documents",
        "expenses",
        "baby",
        "pets",
        "automation",
        "integrations",
        "notifications",
        "account",
        "weather",
        "contracts",
        "decisions",
        "wishlists",
        "inbox",
        "loyalty",
        "birthdays",
    }
)
PRODUCT_ACTIONS = frozenset({"open", "create", "update", "complete", "delete", "search", "export"})
PRODUCT_RESULTS = frozenset({"success", "error", "cancel"})
PRODUCT_ROUTE_FAMILIES = frozenset(
    {
        "home",
        "todo",
        "tasks",
        "shopping",
        "routines",
        "notes",
        "documents",
        "board",
        "birthdays",
        "trips",
        "decisions",
        "wishlists",
        "baby",
        "pets",
        "more",
        "calendar",
        "weather",
        "expenses",
        "contracts",
        "inbox",
        "integrations",
        "automations",
        "members",
        "profile",
        "notifications",
        "loyalty",
    }
)
PRODUCT_DURATION_BUCKETS = frozenset({"none", "lt_100ms", "100_500ms", "500_2000ms", "gt_2000ms"})
PRODUCT_EVENT_FIELDS = frozenset({"kind", "feature", "action", "result", "route_family", "duration_bucket"})


@dataclass(frozen=True)
class ProductAnalyticsConfig:
    enabled: bool
    base_url: str
    site_id: str
    app_origin: str
    timeout: float

    @property
    def configured(self):
        return bool(self.enabled and self.base_url and self.site_id and self.app_origin)


def get_product_analytics_config():
    return ProductAnalyticsConfig(
        enabled=bool(getattr(settings, "MATOMO_TRACKING_ENABLED", False)),
        base_url=str(getattr(settings, "MATOMO_BASE_URL", "") or "").strip().rstrip("/"),
        site_id=str(getattr(settings, "MATOMO_SITE_ID", "") or "").strip(),
        app_origin=str(getattr(settings, "MATOMO_TRACKING_APP_ORIGIN", "") or "").strip().rstrip("/"),
        timeout=float(getattr(settings, "MATOMO_TRACKING_TIMEOUT", 4) or 4),
    )


def validate_product_event(payload):
    if not isinstance(payload, dict):
        raise ProductAnalyticsSchemaError("invalid_payload")
    unknown = set(payload) - PRODUCT_EVENT_FIELDS
    if unknown:
        raise ProductAnalyticsSchemaError("unknown_field")

    clean = {
        "kind": str(payload.get("kind") or ""),
        "feature": str(payload.get("feature") or ""),
        "action": str(payload.get("action") or ""),
        "result": str(payload.get("result") or ""),
        "route_family": str(payload.get("route_family") or ""),
        "duration_bucket": str(payload.get("duration_bucket") or "none"),
    }
    if clean["kind"] not in PRODUCT_KINDS:
        raise ProductAnalyticsSchemaError("invalid_kind")
    if clean["feature"] not in PRODUCT_FEATURES:
        raise ProductAnalyticsSchemaError("invalid_feature")
    if clean["action"] not in PRODUCT_ACTIONS:
        raise ProductAnalyticsSchemaError("invalid_action")
    if clean["result"] not in PRODUCT_RESULTS:
        raise ProductAnalyticsSchemaError("invalid_result")
    if clean["route_family"] not in PRODUCT_ROUTE_FAMILIES:
        raise ProductAnalyticsSchemaError("invalid_route_family")
    if clean["duration_bucket"] not in PRODUCT_DURATION_BUCKETS:
        raise ProductAnalyticsSchemaError("invalid_duration_bucket")
    if clean["kind"] == "pageview" and (clean["action"] != "open" or clean["result"] != "success"):
        raise ProductAnalyticsSchemaError("invalid_pageview_semantics")
    return clean


def _tracking_url(config):
    parsed = urlsplit(config.base_url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ProductAnalyticsError("Matomo tracking requires a valid HTTPS base URL.")
    if parsed.query or parsed.fragment:
        raise ProductAnalyticsError("Matomo base URL must not contain a query or fragment.")
    return f"{config.base_url}/matomo.php"


def _normalized_action_url(config, route_family):
    parsed = urlsplit(config.app_origin)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        raise ProductAnalyticsError("Tracking app origin is invalid.")
    if parsed.query or parsed.fragment:
        raise ProductAnalyticsError("Tracking app origin must not contain a query or fragment.")
    return urlunsplit((parsed.scheme, parsed.netloc, f"/analytics/{route_family}", "", ""))


def _tracking_params(config, event):
    params = {
        "idsite": config.site_id,
        "rec": "1",
        "apiv": "1",
        "rand": str(secrets.randbelow(2_147_483_647)),
        "action_name": f"FamilyOS/{event['route_family']}",
        "url": _normalized_action_url(config, event["route_family"]),
    }
    if event["kind"] == "event":
        params.update(
            {
                "e_c": f"familyos.{event['feature']}",
                "e_a": event["action"],
                "e_n": f"{event['result']}:{event['duration_bucket']}",
            }
        )
    return params


def dispatch_product_event(payload):
    event = validate_product_event(payload)
    config = get_product_analytics_config()
    if not config.enabled:
        return False
    if not config.configured:
        raise ProductAnalyticsError("Matomo product tracking is not fully configured.")

    request = Request(
        _tracking_url(config),
        data=urlencode(_tracking_params(config, event)).encode("utf-8"),
        headers={"Content-Type": "application/x-www-form-urlencoded", "User-Agent": "FamilyOS-ProductAnalytics/1.0"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=config.timeout):
            pass
    except HTTPError as exc:
        raise ProductAnalyticsError(f"Matomo tracking HTTP error {exc.code}.") from exc
    except (URLError, TimeoutError) as exc:
        raise ProductAnalyticsError("Matomo product tracking is currently unavailable.") from exc
    return True
