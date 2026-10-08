<p align="center"><img src="frontend/public/brand/logo-primary.svg" alt="fam-uh-le" width="520"></p>

# fam-uh-le

**Familie. Organisiert. Gemeinsam.**

Mobile-first Family OS als installierbare PWA: gemeinsame Aufgaben, Einkäufe, Routinen, Kalender, Inbox und öffentliche Datenquellen in einer Oberfläche. Deutsch und Englisch sind ab Werk enthalten; weitere Sprachen können über i18next ergänzt werden.

## Funktionsumfang

- Familien und Rollen: Owner, Erwachsene, Teenager, Kinder, Gäste
- gemeinsame Aufgaben inkl. Fälligkeit, Priorität und Erledigen
- gemeinsame Einkaufslisten
- **Zuletzt gemacht** mit Intervallen und Verlauf
- Kalenderansicht für interne und importierte Ereignisse
- Inbox für Inhalte aus Share-Sheet, Browsern und Messengern
- Inbox → Aufgabe / Einkauf mit einem Tap
- Integrationsverwaltung inkl. manuellem Sync
- sicherer HTTPS-only ICS/iCal- und Müllkalender-Adapter
- normalisiertes Eventmodell für weitere öffentliche Daten
- JWT-Login mit automatischem Token-Refresh
- PWA mit Share Target, Offline-Shell und Maskable Icon
- responsive Mobile-first UI + Desktop-Erweiterung
- globales wiederverwendbares Designsystem
- Django Admin
- PostgreSQL
- Docker Compose
- Caddy als Reverse Proxy und Static Host mit automatischem Let's Encrypt
- CI für React-Build, Django-Checks/Tests und Docker-Build

## Branding

Die Markenassets liegen unter `frontend/public/brand/`:

- `logo-primary.svg` – vollständige Wort-/Bildmarke
- `icon.svg` – reguläres App-Icon
- `icon-maskable.svg` – PWA/Android Maskable Icon
- `frontend/public/logo.svg` – kompakte kompatible Icon-Variante

Die PWA verwendet die finalen Icons direkt im Manifest; Login und Navigation greifen ebenfalls auf diese Assets zurück.

## Architektur

```text
Browser / installierte PWA
        │
        ▼
      Caddy ─────────────── React Static Build
        │
        ├── /api/* ─────── Django REST API
        ├── /admin/* ───── Django Admin
        └── /static/* ──── Django Static Files
                              │
                              ▼
                          PostgreSQL

ICS / Müll / Warnungen / Messenger / weitere Adapter
                         │
                         ▼
                  IntegrationSource
                         │
                         ▼
                    FamilyEvent
                         │
                  Kalender / Inbox
                         │
                         ▼
               Aufgaben · Einkauf · UI
```

## Deployment

```bash
cp .env.example .env
# DOMAIN, DJANGO_SECRET_KEY, POSTGRES_PASSWORD und Admin-Zugang setzen
docker compose up -d --build
```

DNS A/AAAA muss auf den Docker-Host zeigen. Caddy lauscht auf **80/443**, holt und erneuert das TLS-Zertifikat automatisch und persistiert Zertifikatsdaten im `caddy_data` Volume.

Ein erster Haushalt, eine Einkaufsliste und sinnvolle Standardroutinen werden beim initialen Setup idempotent erzeugt.

## Öffentliche Daten

In Django Admin oder über die REST-API kann eine `IntegrationSource` angelegt werden. Für ICS/Müllkalender:

- `kind`: `ics` oder `waste`
- `endpoint`: öffentliche **HTTPS**-URL
- optional `config`: `{ "event_type": "waste.collection" }`

Synchronisieren geht entweder direkt in der App oder per CLI:

```bash
docker compose exec backend python manage.py sync_integrations
```

Private, Loopback-, Link-Local- und nicht-HTTPS-Ziele werden blockiert. Weitere Adapter wie DWD/NINA, kommunale APIs, Telegram, Schulsysteme oder Home Assistant können an `backend/family/integrations.py` angebunden werden, ohne das Kernmodell oder die UI umzubauen.

## Navigation

Die Primärnavigation bleibt absichtlich auf fünf häufige Bereiche reduziert:

**Heute · Aufgaben · Einkauf · Zuletzt · Mehr**

Unter **Mehr** befinden sich Kalender, Inbox, Integrationen, Familie, Sprache und Logout. Touch-Targets, Safe Areas, Reduced Motion und Desktop-Layout sind Bestandteil des Basissystems.

## Repository

```text
backend/              Django + REST API + Tests
frontend/             React PWA + Designsystem + Brand Assets
docker/               Images
Caddyfile              TLS / Reverse Proxy / Static Routing
docker-compose.yml     Produktionsstack
.github/workflows/     CI
```
