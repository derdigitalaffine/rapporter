# fam-uh-le

**Familie. Organisiert. Gemeinsam.**

`fam-uh-le` is a mobile-first family operating system for collaborative tasks, shopping, household routines and public-data integrations. The product is designed as an installable PWA and ships in German and English.

## Included MVP

- shared family/role model
- collaborative task list with assignment, due dates and completion
- shared shopping lists and live item state
- **Zuletzt gemacht / Recently done** routines with history and suggested intervals
- normalized family events for calendars and public data
- integration sources with a secure HTTPS-only ICS/iCal adapter
- family inbox model for share-sheet / messenger ingestion
- JWT authentication
- responsive mobile-first React interface
- offline-capable PWA shell
- German and English i18n
- reusable global design tokens/components
- Django admin for operational configuration
- PostgreSQL persistence
- Docker Compose production deployment
- Caddy reverse proxy + automatic HTTPS/Let's Encrypt
- GitHub Actions build checks

## Architecture

```text
Browser / installed PWA
        │
        ▼
      Caddy ─────────────── static React build
        │
        ├── /api/* ─────── Django REST API
        ├── /admin/* ───── Django Admin
        └── /static/* ──── Django static files
                              │
                              ▼
                          PostgreSQL
```

External data is normalized before it reaches the UI:

```text
ICS / waste calendar / warnings / messenger adapters
                    │
                    ▼
           IntegrationSource
                    │
                    ▼
              FamilyEvent
                    │
             Rules / Inbox
                    │
                    ▼
        tasks · reminders · UI
```

## Production deployment

1. Point the DNS A/AAAA record of your domain to the Docker host.
2. Copy the environment template:

```bash
cp .env.example .env
```

3. Set at least `DOMAIN`, `DJANGO_SECRET_KEY`, `POSTGRES_PASSWORD` and a strong initial admin password.
4. Start the stack:

```bash
docker compose up -d --build
```

Caddy listens on ports **80/443**, obtains and renews the public TLS certificate automatically when `DOMAIN` resolves to the host, and persists certificate state in the `caddy_data` volume.

A first household, shopping list and sensible household routines are bootstrapped idempotently when the initial admin credentials are configured.

## Login

Open `https://<DOMAIN>` and sign in with `DJANGO_SUPERUSER_USERNAME` / `DJANGO_SUPERUSER_PASSWORD`. Operational configuration is available at `/admin/`.

## Public-data integrations

Create an `IntegrationSource` in Django Admin. For an ICS/iCal source use:

- kind: `ics` or `waste`
- endpoint: a **public HTTPS** calendar URL
- optional config: `{ "event_type": "waste.collection" }`

Then run:

```bash
docker compose exec backend python manage.py sync_integrations
```

The adapter rejects private, loopback, link-local and non-HTTPS targets to reduce SSRF risk. Additional adapters (DWD/NINA, municipal APIs, Telegram, school systems, Home Assistant) can plug into `family/integrations.py` without changing the domain/UI model.

## Product design

The primary navigation is deliberately limited to five high-frequency areas:

**Heute · Aufgaben · Einkauf · Zuletzt · Mehr**

Touch targets, safe-area handling, reduced-motion support, installability and desktop expansion are part of the base design system. Brand assets live in `frontend/public/logo.svg`.

## Repository layout

```text
backend/              Django + REST API
frontend/             React PWA
docker/               image definitions
Caddyfile              TLS/reverse proxy/static routing
docker-compose.yml     production stack
.github/workflows/     CI
```

## Development direction

Next adapters/modules are intentionally separable: weather/warnings, municipal waste discovery, messenger share ingestion, calendars, school data, notifications, household automation and rules. The API model is already structured so these features do not need to be hard-wired into the task or shopping modules.
