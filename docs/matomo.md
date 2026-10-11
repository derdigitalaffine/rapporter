# Matomo integration

FamilyOS supports optional external Matomo reporting for Superadmin and optional privacy-bounded product tracking. Both integrations are server-to-server. Reporting and tracking are separate contracts and can be disabled without affecting core FamilyOS functionality.

## Backend configuration

```env
MATOMO_BASE_URL=https://analytics.example.com
MATOMO_SITE_ID=1
MATOMO_AUTH_TOKEN=replace-with-read-only-reporting-token
MATOMO_API_TIMEOUT=8

# Product tracking is OFF unless explicitly enabled.
MATOMO_TRACKING_ENABLED=false
# Defaults to APP_URL when blank. Only the origin is used; FamilyOS replaces
# paths, query strings and fragments with /analytics/<route-family>.
MATOMO_TRACKING_APP_ORIGIN=https://familyos.example.com
MATOMO_TRACKING_TIMEOUT=4
```

`MATOMO_AUTH_TOKEN` is used only for Superadmin reporting. Product tracking does not send that token to Matomo and never exposes it to the browser.

## Reporting architecture

The browser never receives `MATOMO_AUTH_TOKEN`. Superadmin calls FamilyOS endpoints under `/api/superadmin/analytics/matomo/`; Django then calls Matomo's Reporting API server-to-server and returns only bounded aggregate datasets.

The first dashboard includes:

- visits and unique visitors
- actions and average visit duration
- daily visit trend
- top page URLs
- referrer types
- event categories

The reporting API deliberately does not expose raw visits, visitor IDs, IP addresses or arbitrary custom dimensions.

## Product tracking decision

FamilyOS uses a **server-side event gateway**, not the Matomo JavaScript tracker and not Matomo Tag Manager. The authenticated browser sends a small versioned event to `/api/analytics/product-event/`; Django validates it against a fixed allowlist and then calls Matomo's Tracking HTTP API.

This choice is privacy-first:

- no Matomo script, cookie or tracking origin is loaded by the browser
- no Matomo CSP exception is required
- no `uid`, `cid`, `_id`, client IP override, referrer or reporting token is sent
- FamilyOS does not create a stable analytics visitor ID or fingerprint
- Matomo therefore sees the FamilyOS server as the network source; do not interpret unique/returning visitor or retention metrics as user-level product truth for this capture mode
- pageview and event counts remain useful, but cross-session funnels/retention are intentionally less precise

### Consent / legal-basis policy

Product analytics is disabled by default (`MATOMO_TRACKING_ENABLED=false`). Enabling it is an explicit deployment decision. FamilyOS itself does not set analytics cookies or create a durable visitor identity in this mode, so there is no FamilyOS analytics-consent cookie/banner state to persist. Operators must still determine and document the applicable legal basis for their deployment; where consent is required, leave tracking disabled until an appropriate consent mechanism and policy are in place.

Changing later to a JavaScript tracker, durable visitor ID, fingerprinting, session replay, heatmaps or Tag Manager is a separate privacy/security change and must not be done through configuration alone.

## Versioned product-event boundary

The v1 request accepts only these fields:

- `kind`: `pageview` or `event`
- `feature`: fixed product feature key
- `action`: `open`, `create`, `update`, `complete`, `delete`, `search`, `export`
- `result`: `success`, `error`, `cancel`
- `route_family`: fixed FamilyOS route family
- `duration_bucket`: `none`, `lt_100ms`, `100_500ms`, `500_2000ms`, `gt_2000ms`

Unknown fields or enum values are rejected. Pageviews are restricted to `open` + `success` semantics. The SPA bridge derives the route family from FamilyOS navigation and sends a synthetic Matomo URL such as `https://familyos.example.com/analytics/documents`; the real path suffix, query string and fragment never cross the gateway.

Never add the following to the taxonomy or Matomo payload:

- email addresses, usernames, family/member names or IDs
- document/file/attachment names or contents
- search terms, notes or other free text
- health, pregnancy/baby or pet content
- invite/reset/auth tokens
- full URLs, query strings, fragments or referrers
- audit/security events from the canonical #204 telemetry subsystem

## Failure behavior

Analytics is optional and fail-open. Invalid client payloads receive a validation error, but Matomo outages or incomplete external configuration do not break FamilyOS actions. The backend logs only an error class and does not reflect vendor error text to the browser.

## Matomo-side privacy and retention

FamilyOS's egress boundary is only one layer. The external Matomo instance should also be configured with privacy-minimizing settings appropriate to the deployment:

- enable IP anonymization/masking and avoid retaining proxy/web-server logs longer than necessary
- use the shortest practical raw-visit retention and scheduled data deletion
- restrict Matomo access to operators who need analytics
- keep session recording, heatmaps and unrelated data-enrichment plugins disabled unless separately reviewed
- do not create custom dimensions that reintroduce FamilyOS identifiers or private content
- document the Matomo host, processor/controller roles, retention window and lawful basis in the deployment privacy documentation

## CSP and network boundary

No browser CSP change is needed for product tracking because browsers contact only the existing FamilyOS API origin. Only the Django backend contacts `MATOMO_BASE_URL`, which must be HTTPS and must not contain credentials, query parameters or fragments.

## Rollback

Set `MATOMO_TRACKING_ENABLED=false` to stop new product analytics egress immediately. Removing reporting configuration separately disables the Superadmin Matomo dashboard; neither action changes FamilyOS tenant data or the internal #204 telemetry/audit records.
