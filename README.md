<p align="center"><img src="frontend/public/brand/logo-primary.svg" alt="FamilyOS" width="520"></p>

# FamilyOS

**Familie. Organisiert. Gemeinsam.**

FamilyOS ist ein self-hosted, mobile-first Family Operating System als installierbare PWA. Aufgaben, Einkäufe, Routinen, Kalender, Familien-Inbox, Bonuskarten, Einladungen, öffentliche Daten, Smart-Home-/Mobilitätsdaten und Wenn→Dann-Automationen laufen in einer gemeinsamen Oberfläche. Deutsch und Englisch sind integriert.

## Anwenderhandbuch

Du möchtest FamilyOS im Alltag nutzen? Im **[Anwenderhandbuch](docs/user-guide/README.md)** findest du kurze Schritt-für-Schritt-Anleitungen im Du-Ton – inklusive Screenshots für die wichtigsten Abläufe.

Dort geht es unter anderem um **Heute**, Aufgaben, Einkauf, Kalender, Routinen, Familie und Rechte, Mitteilungen, Integrationen, Automationen, Bonuskarten sowie PWA- und Offline-Nutzung.

## Schnellstart

```bash
./scripts/setup.sh
```

Der `dialog`/`whiptail`-Wizard erzeugt `.env`, sichert vorhandene Konfigurationen und kann den Stack direkt starten. Er richtet außerdem zwei bewusst getrennte Zugänge ein:

- **Superadmin** – globaler Plattformzugang für Familien-Tenants; gehört keiner Familie an.
- **Familien-Owner** – normaler Owner-Zugang der ersten Familie.

Das Setup führt außerdem durch Betriebsmodus, Domain/IP, Ports, Zeitzone, Sprache, erste Familie, PostgreSQL, Scheduler-Intervall sowie optional Google-/Microsoft-Kalender-OAuth. Die serverseitige Web-Push-Infrastruktur wird automatisch vorbereitet; die Benachrichtigungsberechtigung bleibt weiterhin eine bewusste Browser-/Benutzerentscheidung.

Transaktionale E-Mail ist bei neuen Installationen absichtlich deaktiviert (`dummy`-Backend). Für SMTP kann anschließend der sichere Helper verwendet werden; das Passwort wird dabei nicht ausgegeben:

```bash
bash scripts/configure-mail.sh
```

Details zu SMTP, Worker, Retry/Idempotenz sowie SPF/DKIM/DMARC stehen in **[docs/operator/email.md](docs/operator/email.md)**.

### Betriebsmodi

- `internal`: internes HTTPS mit Caddys lokaler CA
- `public`: öffentliches HTTPS direkt in Caddy via ACME / Let's Encrypt
- `proxy`: HTTP hinter einem vorhandenen Reverse Proxy, der TLS terminiert

Modus später umschalten:

```bash
./scripts/tls-mode.sh public
./scripts/tls-mode.sh internal
./scripts/tls-mode.sh proxy
```

## Mehrfamilienfähigkeit

Jede Familie ist ein eigener Tenant. Familienbezogene Daten sind immer einer `Family` zugeordnet; Zugriffe laufen über `Membership` und werden serverseitig auf die Familienmitgliedschaft begrenzt.

Der globale Superadmin erhält nach dem Login eine eigene FamilyOS-Verwaltungsoberfläche. Dort kann er:

- Familien-Tenants anlegen,
- Owner-Einladungen erzeugen,
- den Status eines Tenants sehen,
- Familien sperren und wieder aktivieren.

Eine neu angelegte Familie besitzt keine implizite Verbindung zum Superadmin. Der zukünftige Familieninhaber registriert sich über die Owner-Einladung und wird ausschließlich Owner dieses Tenants. Normale Owner/Erwachsene können weiterhin Familienmitglieder einladen, aber keine Owner-Einladung erzeugen.

Die Tenant-Struktur ist bewusst providerunabhängig gehalten. Spätere Tarife/Subscriptions können an die Familie angehängt werden, ohne die Familienisolation neu zu entwerfen; Payment-Funktionen selbst sind derzeit nicht Teil des Cores.

## Familie & Einladungen

Unter **Mehr → Familie** können Owner/Erwachsene Mitglieder verwalten, Rollen ändern und Einladungslinks teilen. Einladungen sind einmal verwendbar und standardmäßig sieben Tage gültig. E-Mail-gebundene Einladungen können nur mit der vorgesehenen Adresse angenommen werden. Der letzte Owner kann nicht entfernt oder heruntergestuft werden.

## Aufgaben, Einkäufe & Routinen

FamilyOS führt ein lokales Familien-Gedächtnis in PostgreSQL. Frühere Aufgaben und Einkaufsartikel werden nach Häufigkeit und Aktualität vorgeschlagen. Gemerkte Details bleiben erhalten, wenn ein aktiver Eintrag gelöscht wird.

- Aufgabenlisten, Prioritäten, Fälligkeit, Zuständigkeit, Dauer und Wiederholung
- Einkaufslisten, Mengen, Kategorien, Bereiche und Favoriten
- Quick-Add mit Deduplizierung bzw. Wiederöffnung vorhandener Einträge
- wiederkehrende Routinen mit Erledigungsprotokoll

## Bonuskarten & Barcodes

Bonuskarten können mit ausgewählten Familienmitgliedern geteilt und offline an der Kasse geöffnet werden. Rendering und Erkennung erfolgen lokal im Browser. Der Scanner unterstützt 2D-Codes sowie gängige 1D-Symbologien, insbesondere **EAN-13, EAN-8, UPC-A/UPC-E, Code 128, Code 39 und ITF**.

Wenn der native `BarcodeDetector` eines Browsers 1D-Formate nicht vollständig unterstützt, aktiviert FamilyOS automatisch den lokalen ZXing-Fallback. Damit bleibt die 1D-Erkennung auch auf Browsern nutzbar, die nativ beispielsweise nur QR-Codes erkennen.

## Kalender & Integrationen

Unter **Mehr → Integrationen** gibt es einen geführten Katalog. Quellen können einzeln oder gemeinsam synchronisiert werden; Fehlerstatus und Retry-Zeitpunkte werden gespeichert.

Unterstützt werden unter anderem:

- generisches ICS/iCal
- Google Calendar und Microsoft 365 via read-only OAuth oder ICS
- WebUntis und Moodle via iCal
- Stadt/Landkreis Kaiserslautern Abfallkalender; für die Stadt kann eine heruntergeladene `.ics`-Datei hochgeladen werden
- DWD-Wetterwarnungen, NINA/warnung.bund.de und Open-Meteo
- Home Assistant
- VRN-Abfahrten
- Telegram und PWA Share Target

## Wenn → Dann

Owner und Erwachsene können Regeln vollständig in der App erstellen. Beispiele für Trigger sind Müllabfuhr, Frost/Regen, amtliche Warnungen, Termine, Home-Assistant-Zustände, ÖPNV-Verspätungen und erledigte Aufgaben. Aktionen können Aufgaben, Einkaufsartikel, Inbox-Hinweise, Home-Assistant-Services oder Web Push auslösen.

Scheduler und Integrations-Syncs laufen tenantbezogen; gesperrte Familien werden beim Integrations-Scheduler nicht synchronisiert.

## PWA & Push

FamilyOS enthält 192/512-PNG-App-Icons, maskable Varianten, Install-Flow, PWA-Shortcuts und Share Target. Der Service Worker cached keine `/api/`, `/admin/` oder privaten Nutzerdaten.

Das Setup erzeugt automatisch ein P-256-VAPID-Schlüsselpaar und speichert es ausschließlich in `.env`. Bei einem erneuten Setup bleibt ein vorhandenes gültiges Paar unverändert, damit bereits registrierte Browser-Subscriptions nicht durch unnötige Schlüsselrotation beschädigt werden. Fehlende oder inkonsistente VAPID-Werte können auf bestehenden Installationen nicht-interaktiv repariert werden:

```bash
bash scripts/ensure-vapid.sh
docker compose restart backend
```

Der private VAPID-Key wird nie über die API ausgeliefert. Im Browser bleibt Web Push opt-in: Erst wenn ein Nutzer Benachrichtigungen aktiviert, wird die Browser-Berechtigung angefragt.

## Auth & Sicherheit

- JWT Access/Refresh in `HttpOnly`, `SameSite=Lax` Cookies
- automatische Session-Erneuerung
- serverseitige Tenant-Isolation über Familienmitgliedschaften
- getrennte globale Superadmin-Rolle
- gesperrte Tenants verlieren den normalen App-Zugriff
- Assignees, Listenwechsel, Freigaben und Integrationen werden gegen die Familienzugehörigkeit geprüft
- Connector-Secrets/OAuth-Tokens werden in API-Antworten maskiert
- externe Connector-Ziele sind gegen private/Loopback/Link-Local-Adressen geschützt; Home Assistant ist die bewusste LAN-Ausnahme
- Caddy setzt CSP, Frame-/MIME-/Referrer-/Permissions-Sicherheitsheader
- `.env` erhält im Setup Dateirechte `600`
- kein Werbetracking und keine Datenweitergabe im Self-Hosted-Core

## Backup & Restore

```bash
./scripts/backup.sh
./scripts/restore.sh backups/famuhle-YYYYMMDD-HHMMSS.dump
```

Der technische Datenbank-/Dateipräfix `famuhle` bleibt aus Kompatibilitätsgründen erhalten und ist kein sichtbarer Produktname.

## Deployment

```bash
cp .env.example .env
# empfohlen: ./scripts/setup.sh
docker compose up -d --build
```

Compose enthält PostgreSQL, Django, Integrations-/Regel-Scheduler, Notification-/Mail-/Receipt-Worker und Caddy. Im `internal`/`public`-Betrieb wird `docker-compose.override.yml` für HTTPS verwendet. Im `proxy`-Betrieb veröffentlicht der Basis-Compose nur den konfigurierten HTTP-Upstream.

## CI

GitHub Actions prüft unter anderem:

- React Production Build
- Django `makemigrations --check --dry-run`, Migrationen und System Check
- Backend-Regressionstests
- Playwright-E2E inkl. visueller Regressionen
- Setup-/TLS-/Mail-Shell-Syntax und automatische/idempotente VAPID-Erzeugung
- Caddy- und Compose-Konfiguration
- vollständigen Docker-Build

## Repository

```text
backend/                     Django REST API, Tenants, Regeln, Integrationen, Tests
frontend/                    React PWA, Superadmin UI, Brand/PWA Assets
scripts/setup.sh             interaktiver Setup-Wizard
scripts/configure-mail.sh    SMTP-Konfiguration ohne Secret-Ausgabe
scripts/ensure-vapid.sh      idempotente VAPID-Prüfung/Reparatur
scripts/tls-mode.sh          Betriebsmodus internal/public/proxy
scripts/backup.sh            PostgreSQL-Backup
scripts/restore.sh           PostgreSQL-Restore
docs/operator/email.md       Transaktionale Mail: Betrieb, Retry und Zustellbarkeit
docker-compose.yml           Basisstack
.github/workflows/           CI
```