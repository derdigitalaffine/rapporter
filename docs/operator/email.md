# Transactional email

FamilyOS sends security and account email through a durable server-side outbox. The application never requires an external mail SaaS: a normal SMTP server is sufficient.

## Safe default

New installations default to:

```env
EMAIL_BACKEND=django.core.mail.backends.dummy.EmailBackend
```

This means no message leaves the instance and message bodies are not printed to container logs. Configure SMTP explicitly before enabling email-driven account flows.

## Production SMTP

FamilyOS supports two configuration sources:

1. **Superadmin-managed SMTP** in the global Superadmin UI. When enabled, this source takes precedence over the environment fallback.
2. **Environment SMTP** in `.env` / the deployment secret store. This remains the fallback whenever the managed configuration is disabled.

Both routes use the same transactional mail service and outbox for normal application email.

Environment example:

```env
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp.example.com
EMAIL_PORT=587
EMAIL_HOST_USER=familyos@example.com
EMAIL_HOST_PASSWORD=replace-with-a-secret
EMAIL_USE_TLS=true
EMAIL_USE_SSL=false
EMAIL_TIMEOUT=10
DEFAULT_FROM_EMAIL=FamilyOS <familyos@example.com>
SERVER_EMAIL=FamilyOS <familyos@example.com>
EMAIL_REPLY_TO=
APP_URL=https://family.example.com
```

Use either `EMAIL_USE_TLS=true` (usually port 587) or `EMAIL_USE_SSL=true` (usually port 465), never both. `python manage.py check --tag mailing` validates the most important environment combinations.

`APP_URL` is the trusted public origin used to build links. Transactional mail resolvers return only relative application paths; the outbox does not accept arbitrary absolute URLs.

### Superadmin-managed SMTP

The global Superadmin can configure SMTP host, port, username, password, transport security, timeout, From address and optional Reply-To address. Saving changes and sending a test message are sensitive actions and therefore use the existing Superadmin fresh-session and abuse-protection path.

The password is encrypted at rest and is never returned by the API or rendered back into the UI. A blank password field keeps the currently stored secret; the API supports an explicit clear operation rather than treating an empty field as deletion.

The managed SMTP credential is encrypted using key material derived from the Django application secret. Rotating `DJANGO_SECRET_KEY` invalidates the existing managed SMTP ciphertext, so re-enter the SMTP password after such a rotation. Environment-based SMTP is unaffected by this database ciphertext rule.

The Superadmin test mail sends through the currently effective transport and reports success only when a configured backend accepts the message. Dummy or otherwise unconfigured transports return `mail_not_configured`; they are never reported as a successful SMTP test.

## Secrets

For environment SMTP, credentials belong only in `.env` / the deployment secret store. Keep `.env` permission-restricted and do not commit it.

For Superadmin-managed SMTP, the password is stored only as encrypted ciphertext in the singleton mail configuration row. API responses expose only a `password_set` state, never the password or ciphertext. SMTP credentials must not be written to logs, telemetry, health endpoints or error responses.

## Worker

Docker Compose runs a dedicated `mail-worker`:

```text
python manage.py flush_transactional_email --loop --interval 10
```

A one-off drain is also possible:

```bash
docker compose exec backend python manage.py flush_transactional_email --max 100
```

The worker claims rows with a database lease and `SELECT ... FOR UPDATE SKIP LOCKED`, sends outside the transaction, then finalizes only if it still owns the lease. Expired leases are recoverable after a worker crash.

Retries use bounded exponential backoff. Permanent recipient/authentication failures are not retried indefinitely. Stored errors are reduced to operational classes such as `transport`, `recipient_rejected` or `smtp_auth`; provider response bodies are not persisted.

## Idempotency and privacy

Callers must supply a stable `message_key`. Repeating the same business operation with the same key creates at most one outbox row. Reusing a key for different persistent delivery semantics is rejected rather than silently aliasing two business operations.

The outbox rejects context keys that look like credentials, tokens, passwords or WebAuthn challenges. Token-bearing account links are represented by a non-secret domain reference; the target path is resolved only while rendering the message.

After successful delivery acceptance or a terminal delivery failure, FamilyOS immediately clears the recipient address and render context from the outbox row. Retryable failures retain that payload only while another delivery attempt remains necessary. Operational metadata such as recipient HMAC, template key, timestamps and status can remain for diagnostics and idempotency.

`sent` means the configured mail backend accepted the message. It does **not** claim inbox delivery, opening or reading. The same limitation applies to the Superadmin test mail: it proves transport acceptance, not inbox placement.

## Superadmin account operations and mail journal

The global Superadmin UI also exposes bounded account-support operations that reuse the canonical Identity and Recovery services:

- **Change user email** creates a pending email identity and queues the normal verification message. The current primary address remains authoritative until the user verifies the new address; Superadmin never bypasses verification with a direct primary-email write.
- **Send password reset** queues the same versioned, expiring reset flow used by the public recovery endpoint. Superadmin cannot set or view a user's password or recovery token.
- Both mutations require the existing fresh-session Superadmin protection and produce dedicated audit events that contain only the actor and opaque user target, never the email address or token.

The **Mail journal** is a Superadmin-only operational history built from the durable outbox. It exposes template key, locale, status, attempt count, redacted error class and timestamps. While a retryable delivery still needs its recipient payload, the UI may show only a strongly masked recipient hint. It never returns message bodies, render context, `message_key`, domain references, action tokens, full recipient addresses or SMTP credentials. Once the outbox clears a terminal payload, the journal does not reconstruct that recipient from another data source.

## Development and tests

For local development where seeing mail is useful, use Django's console backend deliberately:

```env
EMAIL_BACKEND=django.core.mail.backends.console.EmailBackend
```

Tests use Django's in-memory backend. Production should not use console mail because it writes message bodies and links to logs.

## Domain authentication

For a public production domain, configure DNS at the domain/mail provider:

- **SPF**: authorize the SMTP service that sends for the envelope/domain.
- **DKIM**: enable signing at the SMTP provider and publish its public selector record.
- **DMARC**: publish a policy aligned with the From domain after SPF/DKIM are working; start with reporting if you need a staged rollout.
- Use SMTP over TLS and verify that the provider certificate/hostname is valid.

FamilyOS does not generate DKIM private keys inside the application because signing belongs at the outbound mail server/provider boundary.

## Operations

`mailing.service.mail_health_summary()` exposes only operational metadata for later Superadmin integration:

- whether a delivery backend is configured,
- queued/retry/failed/sent counts,
- last successful acceptance time,
- recent redacted error classes,
- p50/p95 queue-to-send latency.

It intentionally contains no recipient addresses, subjects, message bodies, SMTP credentials or security tokens.

If mail delivery is temporarily broken, fix the configuration and keep the worker running. Retryable rows resume automatically. Permanently failed rows require a new business operation/message key after the root cause is fixed; do not blindly replay security mail without checking whether its referenced action is still valid.
