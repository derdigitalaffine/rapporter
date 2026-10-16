import hashlib
import json
import threading
import time
from contextlib import contextmanager
from decimal import Decimal, InvalidOperation
from urllib.parse import urlsplit

import requests
from django.conf import settings
from django.core.cache import cache
from django.db import connection


_ATTRIBUTION = "© OpenStreetMap contributors"
_RATE_LOCK = threading.Lock()
_LAST_REQUEST_AT = 0.0
_ADVISORY_LOCK_KEY = 78122301


class ShoppingGeocoderError(Exception):
    pass


def _base_url():
    value = str(getattr(settings, "NOMINATIM_BASE_URL", "https://nominatim.openstreetmap.org") or "").strip().rstrip("/")
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ShoppingGeocoderError("Nominatim provider configuration is invalid.")
    return value


def _cache_key(mode, payload):
    provider = _base_url()
    raw = json.dumps([provider, mode, payload], ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return "shopping-geocoder:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()


@contextmanager
def _rate_slot():
    if not getattr(settings, "NOMINATIM_RATE_LIMIT_ENABLED", True):
        yield
        return
    if connection.vendor == "postgresql":
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_lock(%s)", [_ADVISORY_LOCK_KEY])
        try:
            # Public Nominatim asks clients to stay at or below one request/second.
            # Holding one PostgreSQL advisory lock makes this budget process-wide.
            time.sleep(1.0)
            yield
        finally:
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_advisory_unlock(%s)", [_ADVISORY_LOCK_KEY])
        return

    global _LAST_REQUEST_AT
    with _RATE_LOCK:
        wait = max(0.0, 1.0 - (time.monotonic() - _LAST_REQUEST_AT))
        if wait:
            time.sleep(wait)
        yield
        _LAST_REQUEST_AT = time.monotonic()


def _request(path, params):
    url = f"{_base_url()}/{path.lstrip('/')}"
    headers = {
        "Accept": "application/json",
        "User-Agent": str(getattr(settings, "NOMINATIM_USER_AGENT", "FamilyOS/1.0 shopping-store lookup")).strip(),
    }
    timeout = float(getattr(settings, "NOMINATIM_TIMEOUT", 5.0))
    try:
        with _rate_slot():
            response = requests.get(
                url,
                params=params,
                headers=headers,
                timeout=timeout,
                allow_redirects=False,
            )
    except requests.RequestException as exc:
        raise ShoppingGeocoderError("Location provider is unavailable.") from exc
    if response.is_redirect or response.is_permanent_redirect or response.status_code != 200:
        raise ShoppingGeocoderError("Location provider returned an invalid response.")
    if int(response.headers.get("Content-Length") or 0) > 512_000:
        raise ShoppingGeocoderError("Location provider response is too large.")
    try:
        return response.json()
    except ValueError as exc:
        raise ShoppingGeocoderError("Location provider returned invalid JSON.") from exc


def _bounded_text(value, limit):
    return " ".join(str(value or "").split())[:limit]


def _coordinate(value, minimum, maximum):
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ShoppingGeocoderError("Location provider returned invalid coordinates.") from exc
    if number < minimum or number > maximum:
        raise ShoppingGeocoderError("Location provider returned invalid coordinates.")
    return f"{number:.6f}"


def _candidate(raw):
    address = raw.get("address") if isinstance(raw.get("address"), dict) else {}
    names = raw.get("namedetails") if isinstance(raw.get("namedetails"), dict) else {}
    name = _bounded_text(
        names.get("name")
        or address.get("shop")
        or address.get("amenity")
        or address.get("supermarket")
        or str(raw.get("display_name") or "").split(",")[0],
        120,
    )
    if not name:
        return None
    branch = _bounded_text(
        address.get("city_district")
        or address.get("suburb")
        or address.get("town")
        or address.get("city")
        or address.get("village"),
        120,
    )
    provider_ref = _bounded_text(raw.get("place_id") or f"{raw.get('osm_type', '')}:{raw.get('osm_id', '')}", 160)
    if not provider_ref or provider_ref == ":":
        return None
    latitude = _coordinate(raw.get("lat"), Decimal("-90"), Decimal("90"))
    longitude = _coordinate(raw.get("lon"), Decimal("-180"), Decimal("180"))
    display_label = f"{name} · {branch}" if branch else name
    return {
        "provider": "nominatim",
        "provider_ref": provider_ref,
        "name": name,
        "branch_label": branch,
        "address": _bounded_text(raw.get("display_name"), 240),
        "latitude": latitude,
        "longitude": longitude,
        "display_label": display_label,
    }


def _normalize_rows(rows):
    if isinstance(rows, dict):
        rows = [rows]
    if not isinstance(rows, list):
        raise ShoppingGeocoderError("Location provider returned an invalid payload.")
    result = []
    for row in rows[:5]:
        if not isinstance(row, dict):
            continue
        candidate = _candidate(row)
        if candidate:
            result.append(candidate)
    return result


def search_stores(query):
    query = _bounded_text(query, 160)
    if len(query) < 3:
        raise ValueError("Search query must contain at least three characters.")
    payload = {"q": query}
    key = _cache_key("search", payload)
    cached = cache.get(key)
    if cached is not None:
        return cached
    rows = _request("search", {
        "q": query,
        "format": "jsonv2",
        "addressdetails": 1,
        "namedetails": 1,
        "limit": 5,
    })
    result = _normalize_rows(rows)
    cache.set(key, result, int(getattr(settings, "NOMINATIM_CACHE_SECONDS", 900)))
    return result


def reverse_store(latitude, longitude):
    lat = _coordinate(latitude, Decimal("-90"), Decimal("90"))
    lon = _coordinate(longitude, Decimal("-180"), Decimal("180"))
    payload = {"lat": lat, "lon": lon}
    key = _cache_key("reverse", payload)
    cached = cache.get(key)
    if cached is not None:
        return cached
    row = _request("reverse", {
        "lat": lat,
        "lon": lon,
        "format": "jsonv2",
        "addressdetails": 1,
        "namedetails": 1,
        "zoom": 18,
    })
    result = _normalize_rows(row)
    cache.set(key, result, int(getattr(settings, "NOMINATIM_CACHE_SECONDS", 900)))
    return result


def attribution():
    return _ATTRIBUTION
