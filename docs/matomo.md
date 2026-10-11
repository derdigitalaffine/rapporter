# Matomo integration

FamilyOS supports an optional external Matomo reporting connection for Superadmin. The reporting token is backend-only and must be treated as a secret.

## Backend configuration

```env
MATOMO_BASE_URL=https://analytics.example.com
MATOMO_SITE_ID=1
MATOMO_AUTH_TOKEN=replace-with-read-only-reporting-token
MATOMO_API_TIMEOUT=8
```

With no complete configuration, the integration remains disabled and the rest of Superadmin continues to work.

## Reporting architecture

The browser never receives `MATOMO_AUTH_TOKEN`. Superadmin calls FamilyOS endpoints under `/api/superadmin/analytics/matomo/`; Django then calls Matomo's Reporting API server-to-server and returns only bounded aggregate datasets.

The first dashboard includes:

- visits and unique visitors
- actions and average visit duration
- daily visit trend
- top page URLs
- referrer types
- event categories

The current API deliberately does not expose raw visits, visitor IDs, IP addresses or arbitrary custom dimensions.

## Tracking choices

Reporting and tracking are intentionally separate. Before enabling product tracking, choose one of these approaches:

1. **Matomo JavaScript tracker, consent/cookie mode** — richest visitor, funnel and retention analysis. Requires browser access to the Matomo origin and an explicit privacy/consent decision.
2. **Matomo JavaScript tracker, cookieless mode** — less persistent identification and easier privacy posture, but weaker returning-visitor/retention accuracy.
3. **FamilyOS server-side event gateway** — browser sends an allowlisted product event to FamilyOS, FamilyOS forwards a redacted event to Matomo. Best control over payloads and CSP; visitor attribution requires an explicit pseudonymous-ID policy.
4. **Matomo Tag Manager** — flexible marketing/analytics configuration outside deployments, but increases runtime configurability and therefore needs strict governance and review.

For a family/private-data product, the recommended event payload is metadata-only: feature key, action key, result, coarse duration bucket and route family. Never send family names, email addresses, document titles, free text, attachment names, reset links, invitation tokens or other user content.

## Recommended rollout

Start with this reporting integration and a small fixed event taxonomy. Add tracking only after deciding cookie/consent and visitor-ID policy. In production, use a dedicated Matomo user/token with read-only access to the one configured site whenever possible.
