<p align="center"><img src="frontend/public/brand/logo-primary.svg" alt="fam-uh-le" width="520"></p>

# fam-uh-le

**Familie. Organisiert. Gemeinsam.**

Mobile-first Family OS als installierbare PWA: gemeinsame Aufgaben, Einkäufe, Routinen, Kalender, Inbox und öffentliche Datenquellen in einer Oberfläche. Deutsch und Englisch sind ab Werk enthalten.

## Schnellstart

```bash
bash scripts/setup.sh
```

Der `dialog`/`whiptail`-Wizard erzeugt die vollständige `.env`, sichert vorhandene Konfigurationen und kann den Stack direkt starten. Er fragt TLS, Host/Domain, Zeitzone, Sprache, Familienname, Zugangsdaten, PostgreSQL, Worker und Integrationsintervall ab. Unter **Erweiterte Netzwerkeinstellungen** lassen sich außerdem veröffentlichter HTTP- und HTTPS-Port ändern. Standard: 80/443.

Standardmäßig läuft Caddy mit internem HTTPS (`tls internal`). Für öffentliches ACME/Let's Encrypt:

```bash
bash scripts/tls-mode.sh public
```

Zurück auf internes TLS:

```bash
bash scripts/tls-mode.sh internal
```

Lokale Caddy-CA exportieren:

```bash
bash scripts/export-caddy-ca.sh
```

> Für Let's Encrypt müssen öffentlich normalerweise Port 80 und/oder 443 erreichbar sein. Abweichende veröffentlichte Ports eignen sich vor allem für LAN/self-signed oder wenn ein vorgeschalteter Router/Reverse-Proxy die Standardports weiterleitet.

## Kein Django-Admin für den normalen Betrieb

Alle normalen Familienfunktionen und Integrationen werden in der React-PWA verwaltet. Der Django-Admin bleibt nur als technischer Notfall-/Diagnosezugang erhalten und ist für Einrichtung oder Alltag nicht erforderlich.

Unter **Mehr → Integrationen** gibt es einen geführten Katalog. Eine Verbindung wird beim Anlegen sofort getestet; fehlerhafte Quellen werden nicht gespeichert. Owner und Erwachsene dürfen Integrationen verwalten. Sensitive Werte wie Telegram Bot Tokens werden in API-Antworten maskiert.

## Integrationen

### Müllkalender Kaiserslautern

**Stadt Kaiserslautern:** Der offizielle Stadtbildpflege-Abfallkalender unterstützt individuelle Termine und iCal-Export. In fam-uh-le wird im Integrationskatalog **Müllkalender Stadt Kaiserslautern** gewählt, der offizielle Export geöffnet und die adressbezogene iCal/ICS-URL eingefügt.

**Landkreis Kaiserslautern:** Der Landkreis bietet einen interaktiven Abfuhrplan nach Wohnort und Straße. In fam-uh-le wird **Müllkalender Landkreis Kaiserslautern** gewählt und der adressbezogene Kalenderexport eingebunden.

Nach erfolgreichem Sync erscheinen die Abfuhrtermine im Familienkalender. Für bevorstehende Abfuhren erzeugt fam-uh-le automatisch eine einmalige Aufgabe wie **„Restmüll rausstellen“** für den Vorabend. Duplikate werden verhindert.

### Weitere fertig verdrahtete Adapter

- **ICS/iCal:** beliebige öffentliche HTTPS-Kalender in den Familienkalender importieren.
- **DWD Wetterwarnungen:** amtliche Warnungen nach Region, standardmäßig Kaiserslautern.
- **NINA / Warnung.bund:** getrennte vorkonfigurierte Einträge für Stadt Kaiserslautern und Landkreis Kaiserslautern.
- **7-Tage-Wetter:** Open-Meteo, standardmäßig Kaiserslautern; Koordinaten können im Frontend geändert werden.
- **Telegram Bot:** normale Nachrichten landen in der Inbox; `/todo ...` erzeugt Aufgaben, `/buy ...` bzw. `/einkauf ...` erzeugt Einkaufsartikel.
- **PWA Share Target:** Inhalte aus Browsern und unterstützten Messenger-Apps können über das System-Teilen-Menü an fam-uh-le geschickt und anschließend als Aufgabe oder Einkauf übernommen werden.

Ein eigener `scheduler`-Container synchronisiert aktivierte Quellen regelmäßig. Das Intervall wird im Setup als `INTEGRATION_SYNC_SECONDS` gesetzt (Standard: 300 Sekunden). Zusätzlich gibt es in der App **Alle synchronisieren** und Einzel-Sync.

### Bewusste Grenzen

- **WhatsApp:** kein pauschales Lesen privater Familienchats. Unterstützt wird der datensparsame Share-Target-Flow; eine spätere offizielle Business-Integration wäre ein separater Kanal und kein Chat-Import.
- **Signal:** keine allgemeine offizielle Bot-/Chat-Lese-API; deshalb Share Target statt inoffiziellem Scraping.
- **Kaiserslautern Müllkalender:** fam-uh-le nutzt die offiziellen adressbezogenen Kalenderexports. Es wird bewusst keine undokumentierte interne Website-API reverse-engineered, weil diese jederzeit brechen könnte.
- **Google/Apple/Outlook private Kalender:** generisches ICS funktioniert bereits. OAuth-basierte private Account-Verbindungen sind noch nicht Bestandteil des Self-Hosted-Core.
- **Schulportale/Home Assistant/ÖPNV:** noch keine produktspezifischen Adapter im Core; das normalisierte Integrationsmodell ist dafür vorbereitet.

## Produktfunktionen

- Familien und Rollen: Owner, Erwachsene, Teenager, Kinder, Gäste
- gemeinsame Aufgaben mit Fälligkeit, Priorität und Erledigen
- gemeinsame Einkaufslisten mit Menge und Kategorie
- **Zuletzt gemacht** mit Intervallen und Verlauf
- Familienkalender für interne und importierte Ereignisse
- Inbox für Share Target und Telegram
- Inbox → Aufgabe / Einkauf mit einem Tap
- Integrationskatalog, Test, Sync, Status und Trennen vollständig im Frontend
- automatische Müll-Aufgaben aus Abfuhrterminen
- DWD-/NINA-Warnungen und Wetterdaten im Eventmodell
- JWT-Login mit automatischem Token-Refresh
- PWA mit Offline-Shell, Share Target und Maskable Icon
- responsive Mobile-first UI und wiederverwendbares Designsystem

## Architektur

```text
Browser / installierte PWA
        │
        ▼
      Caddy ─────────────── React Static Build
        │
        ├── /api/* ─────── Django REST API
        └── /static/* ──── Django Static Files
                              │
                              ▼
                          PostgreSQL

Scheduler ──► IntegrationSource ──► Adapter
                                  ├─ ICS / Müll
                                  ├─ DWD
                                  ├─ NINA
                                  ├─ Open-Meteo
                                  └─ Telegram
                                       │
                          FamilyEvent / Inbox / Task / Einkauf
                                       │
                                       ▼
                                   React PWA
```

## Deployment

```bash
cp .env.example .env
# oder empfohlen: bash scripts/setup.sh
docker compose up -d --build
```

Compose enthält PostgreSQL, Django, den Integrations-Scheduler und Caddy. Caddy kann über `HTTP_PORT`/`HTTPS_PORT` auf frei wählbare Host-Ports veröffentlicht werden; intern bleiben 80/443 unverändert.

## Sicherheit

- externe Feed-URLs müssen HTTPS verwenden
- private, Loopback-, Link-Local- und reservierte Ziele werden gegen SSRF blockiert
- Familienobjekte werden serverseitig mandantengetrennt
- Integrationsverwaltung nur für Owner/Erwachsene
- Connector-Secrets werden nicht im Klartext an die UI zurückgegeben
- `.env` wird vom Setup mit Dateirechten `600` geschrieben
- kein Werbetracking und keine Datenweitergabe im Self-Hosted-Core

## CI

GitHub Actions prüft:

- React Production Build
- Django Migration Check
- Django System Check und Tests
- Setup-/TLS-Shell-Syntax
- öffentliche und interne Caddy-Konfiguration
- `docker compose config`
- vollständigen Docker-Build

## Repository

```text
backend/                   Django REST API, Integrationsadapter, Tests
frontend/                  React PWA, Designsystem, Brand Assets
docker/                    Container Images
scripts/setup.sh           interaktiver Erstsetup-Wizard
scripts/tls-mode.sh        TLS-Modus umschalten
scripts/export-caddy-ca.sh lokale Root-CA exportieren
Caddyfile                   öffentliches ACME/Let's Encrypt
Caddyfile.selfsigned        internes TLS
Docker-compose.yml          Produktionsstack inkl. Scheduler
.github/workflows/          CI
```
