<p align="center"><img src="frontend/public/brand/logo-primary.svg" alt="fam-uh-le" width="520"></p>

# fam-uh-le

**Familie. Organisiert. Gemeinsam.**

Mobile-first Family OS als installierbare PWA: gemeinsame Aufgaben, Einkäufe, Routinen, Kalender, Inbox und öffentliche Datenquellen in einer Oberfläche. Deutsch und Englisch sind ab Werk enthalten; weitere Sprachen können über i18next ergänzt werden.

## Schnellstart – empfohlen

Für den ersten Start gibt es einen terminalbasierten Setup-Wizard mit `dialog`/`whiptail`:

```bash
bash scripts/setup.sh
```

Der Wizard fragt Hostname/Domain, TLS-Modus, Zeitzone, Standardsprache, Familienname, Admin-Zugang, PostgreSQL-Konfiguration und Workerzahl ab. Django- und Datenbank-Secrets können automatisch kryptografisch generiert werden. Die erzeugte `.env` wird mit Dateirechten `600` gespeichert; vorhandene Konfigurationen werden vor dem Überschreiben gesichert.

**Standard ist internes HTTPS** über Caddys lokale CA (`tls internal`). Damit kann fam-uh-le zuerst im LAN oder auf einem Testserver betrieben werden, ohne eine öffentliche Domain vorauszusetzen.

### Später auf öffentliches Let's Encrypt umschalten

Sobald DNS A/AAAA auf den Server zeigt:

```bash
bash scripts/tls-mode.sh public
```

Zurück auf internes TLS:

```bash
bash scripts/tls-mode.sh internal
```

Der Helfer aktualisiert Domain, Django Allowed Hosts, CSRF/CORS Origins und die aktive Caddy-Konfiguration und startet Caddy bei laufendem Stack neu.

### Lokale Caddy-CA exportieren

Damit Geräte dem internen Zertifikat ausdrücklich vertrauen können:

```bash
bash scripts/export-caddy-ca.sh
```

Das erzeugte `caddy-local-root.crt` sollte ausschließlich auf Geräten installiert werden, die der eigenen fam-uh-le Installation vertrauen sollen.

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
- Caddy als Reverse Proxy/Static Host; initial internes TLS, optional ACME/Let's Encrypt
- CI für React-Build, Django-Checks/Tests, Shell-Syntax, beide Caddy-Modi und Docker-Build

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

## Manuelles Deployment

Wer den Wizard nicht verwenden möchte:

```bash
cp .env.example .env
# Werte anpassen
docker compose up -d --build
```

`.env.example` startet bewusst mit `Caddyfile.selfsigned`. Für öffentliches TLS `CADDYFILE=Caddyfile` und eine öffentlich auflösbare `DOMAIN` setzen.

Ein erster Haushalt, eine Einkaufsliste und sinnvolle Standardroutinen werden beim initialen Setup idempotent erzeugt. Name, Sprache und Zeitzone der ersten Familie werden aus der `.env` übernommen.

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
backend/                  Django + REST API + Tests
frontend/                 React PWA + Designsystem + Brand Assets
docker/                   Images
scripts/setup.sh           interaktiver Erstsetup-Wizard
scripts/tls-mode.sh        TLS-Modus umschalten
scripts/export-caddy-ca.sh lokale Root-CA exportieren
Caddyfile                  öffentliche ACME/Let's-Encrypt-Konfiguration
Caddyfile.selfsigned       internes/self-signed TLS
Docker-compose.yml         Produktionsstack
.github/workflows/         CI
```
