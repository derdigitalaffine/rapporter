"""SSRF-safe CalDAV requests used by sync/write adapters.

Credentials never leave the validated host. Redirects to another host are rejected,
and callers explicitly opt into accepted HTTP status codes (including 412 conflicts).
"""
import socket
from urllib.parse import urljoin, urlsplit

from .caldav_discovery import (
    REDIRECT_STATUSES,
    CalDavDiscoveryError,
    _basic_authorization,
    _request_once,
    _setting,
    validate_endpoint,
)


WRITE_METHODS = {"PUT", "DELETE", "MKCALENDAR", "PROPPATCH"}
MAX_REQUEST_BYTES = 2 * 1024 * 1024


def safe_request(
    url,
    *,
    username,
    password,
    method,
    body=b"",
    headers=None,
    accepted=(200, 201, 204, 207),
    resolver=socket.getaddrinfo,
):
    method = str(method).upper()
    payload = body.encode("utf-8") if isinstance(body, str) else bytes(body or b"")
    if len(payload) > MAX_REQUEST_BYTES:
        raise CalDavDiscoveryError("caldav_request_too_large")

    current = str(url)
    original_host = urlsplit(current).hostname
    if not original_host:
        raise CalDavDiscoveryError("caldav_url_invalid")
    request_headers = {
        "Authorization": _basic_authorization(username, password),
        "User-Agent": "FamilyOS-CalDAV/1",
        **(headers or {}),
    }
    if payload and "Content-Type" not in request_headers:
        request_headers["Content-Type"] = "application/xml; charset=utf-8"

    max_redirects = int(_setting("CALDAV_MAX_REDIRECTS", 3))
    for redirect_index in range(max_redirects + 1):
        endpoint = validate_endpoint(current, resolver=resolver)
        status, response_headers, response_body = _request_once(
            endpoint,
            method=method,
            body=payload,
            headers=request_headers,
        )
        if status in REDIRECT_STATUSES:
            if redirect_index >= max_redirects:
                raise CalDavDiscoveryError("caldav_redirect_limit")
            location = response_headers.get("Location") or response_headers.get("location")
            if not location:
                raise CalDavDiscoveryError("caldav_redirect_missing_location")
            redirected = urljoin(current, location)
            if urlsplit(redirected).hostname != original_host:
                raise CalDavDiscoveryError("caldav_redirect_host_rejected")
            current = redirected
            continue
        if status in {401, 403}:
            raise CalDavDiscoveryError("caldav_authentication_failed")
        if status not in set(accepted):
            raise CalDavDiscoveryError(f"caldav_http_status_{status}")
        return current, status, response_headers, response_body
    raise CalDavDiscoveryError("caldav_redirect_limit")
