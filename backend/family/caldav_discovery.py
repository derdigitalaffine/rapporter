import base64
import http.client
import ipaddress
import os
import socket
import ssl
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit

from django.conf import settings


DAV = "DAV:"
CALDAV = "urn:ietf:params:xml:ns:caldav"
REDIRECT_STATUSES = {301, 302, 303, 307, 308}


class CalDavDiscoveryError(ValueError):
    pass


@dataclass(frozen=True)
class ValidatedEndpoint:
    url: str
    host: str
    port: int
    ip: str


class _PinnedHTTPConnection(http.client.HTTPConnection):
    def __init__(self, host, *, pinned_ip, port, timeout):
        self._pinned_ip = pinned_ip
        super().__init__(host, port=port, timeout=timeout)

    def connect(self):
        self.sock = socket.create_connection((self._pinned_ip, self.port), self.timeout, self.source_address)


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    def __init__(self, host, *, pinned_ip, port, timeout):
        self._pinned_ip = pinned_ip
        super().__init__(host, port=port, timeout=timeout, context=ssl.create_default_context())

    def connect(self):
        sock = socket.create_connection((self._pinned_ip, self.port), self.timeout, self.source_address)
        # Connect to the validated IP while preserving the original hostname for
        # SNI and certificate verification. DNS cannot be swapped after validation.
        self.sock = self._context.wrap_socket(sock, server_hostname=self.host)


def _setting(name, default):
    configured = getattr(settings, name, None)
    if configured is not None:
        return configured
    raw = os.getenv(name)
    if raw is None:
        return default
    if isinstance(default, bool):
        return raw.strip().lower() in {"1", "true", "yes", "on"}
    if isinstance(default, int):
        return int(raw)
    if isinstance(default, float):
        return float(raw)
    return raw


def _allowed_ports():
    raw = _setting("CALDAV_ALLOWED_PORTS", "443")
    if isinstance(raw, str):
        raw = [value.strip() for value in raw.split(",") if value.strip()]
    try:
        return {int(value) for value in raw}
    except (TypeError, ValueError):
        raise CalDavDiscoveryError("caldav_port_policy_invalid")


def _ip_allowed(address):
    ip = ipaddress.ip_address(address)
    if ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_unspecified or ip.is_reserved:
        return False
    if ip.is_global:
        return True
    return bool(_setting("CALDAV_ALLOW_PRIVATE_NETWORKS", False) and ip.is_private)


def validate_endpoint(url, *, resolver=socket.getaddrinfo):
    try:
        parsed = urlsplit(str(url).strip())
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
    except ValueError as exc:
        raise CalDavDiscoveryError("caldav_url_invalid") from exc
    allowed_schemes = {"https"}
    if _setting("CALDAV_ALLOW_HTTP", False):
        allowed_schemes.add("http")
    if parsed.scheme.lower() not in allowed_schemes or not parsed.hostname:
        raise CalDavDiscoveryError("caldav_url_scheme_rejected")
    if parsed.username is not None or parsed.password is not None:
        raise CalDavDiscoveryError("caldav_url_userinfo_rejected")
    if parsed.fragment:
        raise CalDavDiscoveryError("caldav_url_fragment_rejected")
    if port not in _allowed_ports():
        raise CalDavDiscoveryError("caldav_port_rejected")

    try:
        answers = resolver(parsed.hostname, port, type=socket.SOCK_STREAM)
    except (socket.gaierror, OSError) as exc:
        raise CalDavDiscoveryError("caldav_dns_failed") from exc
    addresses = []
    for answer in answers:
        address = answer[4][0]
        if address not in addresses:
            addresses.append(address)
    if not addresses or any(not _ip_allowed(address) for address in addresses):
        raise CalDavDiscoveryError("caldav_address_rejected")
    return ValidatedEndpoint(url=parsed.geturl(), host=parsed.hostname, port=port, ip=addresses[0])


def _basic_authorization(username, password):
    raw = f"{username}:{password}".encode("utf-8")
    return "Basic " + base64.b64encode(raw).decode("ascii")


def _request_once(endpoint, *, method, body, headers):
    parsed = urlsplit(endpoint.url)
    connection_class = _PinnedHTTPSConnection if parsed.scheme == "https" else _PinnedHTTPConnection
    connection = connection_class(
        endpoint.host,
        pinned_ip=endpoint.ip,
        port=endpoint.port,
        timeout=float(_setting("CALDAV_HTTP_TIMEOUT", 10.0)),
    )
    target = parsed.path or "/"
    if parsed.query:
        target += "?" + parsed.query
    try:
        connection.request(method, target, body=body, headers=headers)
        response = connection.getresponse()
        limit = int(_setting("CALDAV_MAX_RESPONSE_BYTES", 1024 * 1024))
        data = response.read(limit + 1)
        if len(data) > limit:
            raise CalDavDiscoveryError("caldav_response_too_large")
        return response.status, dict(response.getheaders()), data
    except (OSError, ssl.SSLError, http.client.HTTPException) as exc:
        raise CalDavDiscoveryError("caldav_transport_failed") from exc
    finally:
        connection.close()


def safe_propfind(url, *, username, password, depth="0", body=b"", resolver=socket.getaddrinfo):
    current = str(url)
    max_redirects = int(_setting("CALDAV_MAX_REDIRECTS", 3))
    headers = {
        "Authorization": _basic_authorization(username, password),
        "Content-Type": "application/xml; charset=utf-8",
        "Depth": str(depth),
        "User-Agent": "FamilyOS-CalDAV/1",
        "Accept": "application/xml, text/xml",
    }
    for redirect_index in range(max_redirects + 1):
        endpoint = validate_endpoint(current, resolver=resolver)
        status, response_headers, payload = _request_once(
            endpoint, method="PROPFIND", body=body, headers=headers
        )
        if status in REDIRECT_STATUSES:
            if redirect_index >= max_redirects:
                raise CalDavDiscoveryError("caldav_redirect_limit")
            location = response_headers.get("Location") or response_headers.get("location")
            if not location:
                raise CalDavDiscoveryError("caldav_redirect_missing_location")
            current = urljoin(current, location)
            continue
        if status in {401, 403}:
            raise CalDavDiscoveryError("caldav_authentication_failed")
        if status not in {200, 207}:
            raise CalDavDiscoveryError("caldav_http_status")
        return current, payload
    raise CalDavDiscoveryError("caldav_redirect_limit")


def _parse_xml(payload):
    lowered = payload[:4096].lower()
    if b"<!doctype" in lowered or b"<!entity" in lowered:
        raise CalDavDiscoveryError("caldav_xml_unsafe")
    try:
        return ET.fromstring(payload)
    except ET.ParseError as exc:
        raise CalDavDiscoveryError("caldav_xml_invalid") from exc


def _href(root, path):
    node = root.find(path)
    if node is None or not (node.text or "").strip():
        raise CalDavDiscoveryError("caldav_discovery_property_missing")
    return node.text.strip()


PRINCIPAL_BODY = b'''<?xml version="1.0" encoding="utf-8"?>
<d:propfind xmlns:d="DAV:"><d:prop><d:current-user-principal/></d:prop></d:propfind>'''
HOME_BODY = b'''<?xml version="1.0" encoding="utf-8"?>
<d:propfind xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav"><d:prop><c:calendar-home-set/></d:prop></d:propfind>'''
CALENDARS_BODY = b'''<?xml version="1.0" encoding="utf-8"?>
<d:propfind xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav"><d:prop><d:resourcetype/><d:displayname/><c:supported-calendar-component-set/><d:current-user-privilege-set/><d:sync-token/></d:prop></d:propfind>'''


def discover_calendars(*, server_url, username, password, resolver=socket.getaddrinfo, propfind=safe_propfind):
    principal_base, principal_payload = propfind(
        server_url, username=username, password=password, depth="0", body=PRINCIPAL_BODY, resolver=resolver
    )
    principal_root = _parse_xml(principal_payload)
    principal_href = _href(principal_root, f".//{{{DAV}}}current-user-principal/{{{DAV}}}href")
    principal_url = urljoin(principal_base, principal_href)

    home_base, home_payload = propfind(
        principal_url, username=username, password=password, depth="0", body=HOME_BODY, resolver=resolver
    )
    home_root = _parse_xml(home_payload)
    home_href = _href(home_root, f".//{{{CALDAV}}}calendar-home-set/{{{DAV}}}href")
    home_url = urljoin(home_base, home_href)

    calendar_base, calendars_payload = propfind(
        home_url, username=username, password=password, depth="1", body=CALENDARS_BODY, resolver=resolver
    )
    root = _parse_xml(calendars_payload)
    calendars = []
    for response in root.findall(f".//{{{DAV}}}response"):
        if response.find(f".//{{{CALDAV}}}calendar") is None:
            continue
        href_node = response.find(f"{{{DAV}}}href")
        if href_node is None or not (href_node.text or "").strip():
            continue
        name_node = response.find(f".//{{{DAV}}}displayname")
        components = sorted({
            node.attrib.get("name", "").upper()
            for node in response.findall(f".//{{{CALDAV}}}comp")
            if node.attrib.get("name")
        })
        sync_node = response.find(f".//{{{DAV}}}sync-token")
        calendars.append({
            "href": urljoin(calendar_base, href_node.text.strip()),
            "display_name": (name_node.text or "").strip() if name_node is not None else "",
            "components": components,
            "sync_token_supported": bool(sync_node is not None and (sync_node.text or "").strip()),
        })
    return calendars
