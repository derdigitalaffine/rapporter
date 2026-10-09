<p align="center"><img src="frontend/public/brand/logo-primary.svg" alt="fam-uh-le" width="520"></p>

# fam-uh-le

**Familie. Organisiert. Gemeinsam.**

fam-uh-le ist ein self-hosted, mobile-first **Family OS** als installierbare PWA: Aufgaben, Einkäufe, Routinen, Kalender, Familien-Inbox, Einladungen, öffentliche Daten, Smart-Home-/Mobilitätsdaten und Wenn→Dann-Automationen in einer Oberfläche. Deutsch und Englisch sind integriert.

## Schnellstart

```bash
./scripts/setup.sh
```

Alternativ funktioniert weiterhin `bash scripts/setup.sh`.

Der `dialog`/`whiptail`-Wizard erzeugt die `.env`, sichert vorhandene Konfigurationen und kann den Stack direkt starten. Er führt durch Betriebsmodus, Domain/IP, Ports, Zeitzone, Sprache, Familie, Admin, PostgreSQL, Scheduler-Intervall sowie optional Google-/Microsoft-Kalender-OAuth und Web Push.

Es gibt drei Betriebsmodi:

- `internal`: internes HTTPS mit Caddys lokaler CA (`tls internal`)
- `public`: öffentliches HTTPS direkt in Caddy via ACME / Let's Encrypt
- `proxy`: **kein TLS/SSL im fam-uh-le-Stack**; Caddy lauscht nur per HTTP hinter einem eigenen Reverse Proxy, der HTTPS terminiert

Modus später umschalten:

```bash
./scripts/tls-mode.sh public
./scripts/tls-mode.sh internal
./scripts/tls-mode.sh proxy
```

Lokale Caddy-CA exportieren:

```bash
./scripts/export-caddy-ca.sh
```

> Für öffentliches Let's Encrypt müssen normalerweise Port 80 und/oder 443 von außen erreichbar sein. Im `proxy`-Modus veröffentlicht fam-uh-le dagegen standardmäßig nur `127.0.0.1:8080` per HTTP und belegt keinen Host-Port 443.

### Hinter einem eigenen Reverse Proxy

Wähle im Setup `proxy`, wenn Nginx, Traefik, HAProxy, Caddy, Nginx Proxy Manager oder ein anderer vorgeschalteter Proxy bereits Zertifikate/TLS verwaltet. Der Wizard erzeugt dann u. a.:

```dotenv
TLS_MODE=proxy
COMPOSE_FILE=docker-compose.yml
CADDYFILE=Caddyfile.proxy
DOMAIN=fam-uh-le.example.com
PUBLIC_SCHEME=https
PUBLIC_HOST=fam-uh-le.example.com
HTTP_BIND=127.0.0.1
HTTP_PORT=8080
```

Der vorgeschaltete Proxy zeigt auf:

```text
http://127.0.0.1:8080
```

TLS endet ausschließlich am vorgeschalteten Proxy. `Caddyfile.proxy` setzt für Django den öffentlichen Host und `X-Forwarded-Proto: https`, damit Secure-Cookies, CSRF und OAuth-Callback-URLs trotz des internen HTTP-Hops korrekt bleiben.

Beispiel für Nginx auf demselben Host:

```nginx
location / {
    proxy_pass http://127.0.0.1:8080;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-Proto $scheme;
}
```

Läuft der Reverse Proxy auf einem anderen Host oder in einer getrennten Container-Umgebung, setze `HTTP_BIND` auf eine von ihm erreichbare IPv4-Adresse (ggf. `0.0.0.0`) und schütze diesen HTTP-Upstream per Firewall bzw. privatem Netz vor direktem Internetzugriff. Der öffentliche Zugriff muss weiterhin HTTPS verwenden, weil die Anwendung Secure-Cookies und Web-Push verwendet.

## Kein Django-Admin im Alltag

Familienmitglieder, Einladungen, Rollen, Aufgabenlisten, Einkaufslisten, Routinen, Termine, Integrationen, Benachrichtigungen und Regeln werden in der React-PWA verwaltet. Der Django-Admin ist nur technischer Notfallzugang.

## Smarte Aufgaben & Einkäufe

fam-uh-le führt ein **lokales Familien-Gedächtnis** in PostgreSQL. Frühere Aufgaben und Einkaufsartikel werden nach Häufigkeit und Aktualität vorgeschlagen – inklusive gemerkter Details wie Notiz, Priorität, Dauer, Menge, Kategorie und Bereich. Das Gedächtnis bleibt erhalten, wenn der eigentliche Listen-Eintrag später gelöscht wird.

- Aufgabenlisten mit Name, Symbol und Archivierung
- Aufgabe mit Notiz, Priorität, Fälligkeit, Person, Dauer und Wiederholungsfeld
- identische offene Aufgabe wird beim Quick-Add wiederverwendet statt dupliziert
- Einkaufslisten mit Name, Laden, Symbol und Archivierung
- Artikel mit Menge, Kategorie, Bereich, Notiz und Favorit
- bereits abgehakter Artikel wird beim erneuten Hinzufügen wieder geöffnet
- erledigte Einkaufszeilen können aufgeräumt werden, ohne das Familien-Gedächtnis zu verlieren
- übersichtliche Kennzahlen für offen/heute/überfällig/wichtig und offen/erledigt/Favoriten

## Wenn → Dann

Owner und Erwachsene können Regeln vollständig in der App bauen. Der Scheduler prüft die Regeln nach den Integrations-Syncs und protokolliert/dedupliziert Ausführungen.

### Trigger

- Müllabfuhr morgen
- Frost erwartet
- hohe Regenwahrscheinlichkeit
- amtliche DWD-/NINA-Warnung aktiv
- Kalender-/Schultermin steht bevor
- täglich zu einer Uhrzeit
- Home-Assistant-Entity erreicht einen Zustand
- VRN-Abfahrt überschreitet eine Verspätung
- Aufgabe wurde erledigt

### Aktionen

- Aufgabe anlegen
- Einkauf ergänzen
- Familien-Inbox-Hinweis erzeugen
- Home-Assistant-Service ausführen
- Web-Push an registrierte Familiengeräte senden

Vorlagen sind u. a. für Müll rausstellen, Frost/Pflanzen, Warnungen, Regen/Wäsche und ÖPNV-Verspätung enthalten.

## Integrationen

Unter **Mehr → Integrationen** gibt es einen geführten Katalog. Quellen können einzeln oder gemeinsam synchronisiert werden. fam-uh-le speichert letzten Versuch, letzten Erfolg, Fehlertext, Fehlversuche und nächsten automatischen Retry. Der Scheduler verwendet exponentielles Backoff; ein manueller Sync kann sofort testen.

### Kalender

- generisches ICS/iCal
- Google Calendar via read-only OAuth oder privatem iCal-Link
- Microsoft Outlook/Microsoft 365 via read-only OAuth oder ICS
- native Familientermine direkt in fam-uh-le

OAuth ist optional. Ohne eigene OAuth-Client-ID/Secret bleibt ICS vollständig nutzbar. Callback:

```text
https://DEINE-DOMAIN[:PORT]/api/integration-oauth/callback/
```

### Schule

- WebUntis per persönlichem iCal-Abonnement
- Moodle per persönlicher Kalender-iCal-URL

### Müll & öffentliche Daten

- Stadt Kaiserslautern: offizieller adressbezogener iCal/ICS-Export
- Landkreis Kaiserslautern: offizieller adressbezogener Kalenderexport
- DWD Wetterwarnungen
- NINA / warnung.bund.de
- Open-Meteo 7-Tage-Wetter

Die Kaiserslautern-Abfallintegration verwendet bewusst die offiziellen Exporte und keine fragile, undokumentierte Portal-API.

### Messenger

- Telegram Bot: Text → Inbox, `/todo ...` → Aufgabe, `/buy ...` / `/einkauf ...` → Einkauf
- PWA Share Target: Inhalte aus Browser/Messenger über das System-Teilen-Menü an die Familien-Inbox geben

WhatsApp und Signal werden **nicht pauschal mitgelesen**. Dafür bleibt der datensparsame Share-Target-Flow vorgesehen.

### Home Assistant

Eine Home-Assistant-URL, ein Long-Lived Access Token und ausgewählte Entity-IDs können verbunden werden. fam-uh-le liest nur die konfigurierten States. Wenn→Dann-Regeln können zusätzlich einen explizit konfigurierten Home-Assistant-Service aufrufen.

Home Assistant ist die einzige Integration, die bewusst eine private LAN-Adresse ansprechen darf. Externe Feed-Integrationen bleiben gegen private/Loopback/Link-Local-Ziele gesperrt.

### VRN

VRN-Abfahrten werden über die offizielle RapidJSON Departure-Monitor-Schnittstelle angebunden. Haltestelle und optional Linie werden pro Integration festgelegt. Verspätungen können direkt Wenn→Dann-Regeln auslösen.

## Familie & Einladungen

Unter **Mehr → Familie** können Owner/Erwachsene:

- Einladungslinks erzeugen und teilen
- Rolle und optional E-Mail festlegen
- offene Einladungen widerrufen
- Anzeigenamen und Rollen verwalten
- Mitglieder entfernen

Einladungen sind einmal verwendbar und standardmäßig 7 Tage gültig. Eine E-Mail-gebundene Einladung kann nur durch diese Adresse angenommen werden. Der letzte Owner kann nicht entfernt oder heruntergestuft werden.

## Kalender & Routinen

- native Familientermine erstellen, bearbeiten und löschen
- Ort, Notiz und Wiederholungsinformation speichern
- importierte Provider-Ereignisse gemeinsam in der Timeline sehen
- Routinen erstellen, bearbeiten, deaktivieren, löschen und als erledigt protokollieren

## PWA & Push

fam-uh-le enthält echte 192/512-PNG-App-Icons sowie maskable Varianten, Install-Flow, PWA-Shortcuts und Share Target. Der Service Worker cached **keine** `/api/`, `/admin/` oder privaten Nutzerdaten.

Web Push ist im Setup optional. Der Wizard kann VAPID-Schlüssel automatisch erzeugen. Anschließend wird pro Gerät in **Mehr → Benachrichtigungen** einmal die Browserfreigabe erteilt. Push kann direkt als Wenn→Dann-Aktion verwendet werden.

## Auth & Sicherheit

- JWT Access/Refresh liegen in `HttpOnly`, `SameSite=Lax` Cookies statt `localStorage`
- automatische Session-Erneuerung
- Familienobjekte serverseitig strikt mandantengetrennt
- Assignees und Listenwechsel werden gegen die Familienzugehörigkeit geprüft
- externe HTTP-Redirects werden ohne automatisches Redirect-Following erneut validiert
- private/Loopback/Link-Local/reservierte Ziele externer Connectoren sind gesperrt
- Connector-Secrets, OAuth-Tokens und private Kalender-Endpunkte werden in API-Antworten maskiert
- Caddy setzt CSP, Frame-/MIME-/Referrer-/Permissions-Sicherheitsheader
- Service Worker cached keine Auth-/API-Daten
- `.env` erhält im Setup Dateirechte `600`
- kein Werbetracking und keine Datenweitergabe im Self-Hosted-Core

Im `proxy`-Modus ist der interne Hop bewusst unverschlüsseltes HTTP. Deshalb lauscht er standardmäßig nur auf `127.0.0.1`; bei einer abweichenden Bind-Adresse muss der Upstream durch Netzwerkregeln geschützt werden. Öffentlich bleibt HTTPS erforderlich.

## Backup & Restore

Datenbankbackup im PostgreSQL-Custom-Format:

```bash
./scripts/backup.sh
```

Standardziel: `./backups/` (gitignored, Dateien `600`).

Restore ist absichtlich bestätigt/guarded:

```bash
./scripts/restore.sh backups/famuhle-YYYYMMDD-HHMMSS.dump
```

Für automatisierte Wiederherstellung kann nach bewusster Prüfung `--yes` als zweites Argument verwendet werden.

## Architektur

```text
Browser / installierte PWA
        │
        ▼
[optional: eigener Reverse Proxy + TLS]
        │ HTTP im proxy-Modus
        ▼
      Caddy ─────────────── React Static Build
        │
        ├── /api/* ─────── Django REST API
        └── /static/* ──── Django Static Files
                              │
                              ▼
                          PostgreSQL
                              │
     ┌────────────────────────┴───────────────────────┐
     │                                                │
EntryMemory                                  IntegrationSource
Familien-Gedächtnis                               │
                                          Scheduler / Backoff
                                                  │
         ┌──────────────┬──────────┬──────────────┼─────────────┐
       ICS/OAuth       DWD/NINA   Open-Meteo  Home Assistant   VRN/Telegram
                                                  │
                                             FamilyEvent
                                                  │
                                                  ▼
                                          Wenn→Dann Engine
                                  Task / Einkauf / Inbox / HA / Push
```

## Deployment

```bash
cp .env.example .env
# empfohlen: ./scripts/setup.sh
docker compose up -d --build
```

Compose enthält PostgreSQL, Django, Integrations-/Regel-Scheduler und Caddy. Im normalen `internal`/`public`-Betrieb wird `docker-compose.override.yml` automatisch zusätzlich geladen und veröffentlicht den HTTPS-Port. Der Setup-Wizard setzt dafür `COMPOSE_FILE=docker-compose.yml:docker-compose.override.yml`.

Im `proxy`-Betrieb setzt der Wizard dagegen `COMPOSE_FILE=docker-compose.yml`; damit wird nur der HTTP-Port aus dem Basis-Compose veröffentlicht und Host-Port 443 bleibt vollständig frei für den eigenen Reverse Proxy. `HTTP_BIND` und `HTTP_PORT` bestimmen diesen internen Upstream.

## CI

GitHub Actions prüft:

- React Production Build
- Django Migration Check (`makemigrations --check --dry-run`)
- Django System Check
- Regressionstests für Familie, Memory, Automationen, Cookie-Auth, Einladungen, Push und Integrations-Backoff
- Setup-/TLS-Shell-Syntax
- öffentliche, interne und Reverse-Proxy-Caddy-Konfiguration
- Compose-Konfiguration mit TLS **und** im reinen HTTP-Reverse-Proxy-Modus
- vollständigen Docker-Build

## Repository

```text
backend/                     Django REST API, Regeln, Integrationen, Tests
frontend/                    React PWA, FA7 UI, Brand/PWA Assets
docker/                      Container Images
scripts/setup.sh             interaktiver Setup-Wizard
scripts/tls-mode.sh          Betriebsmodus internal/public/proxy umschalten
scripts/export-caddy-ca.sh   lokale Root-CA exportieren
scripts/backup.sh            PostgreSQL-Backup
scripts/restore.sh           PostgreSQL-Restore
Caddyfile                    öffentliches ACME/Let's Encrypt
Caddyfile.selfsigned         internes TLS
Caddyfile.proxy              reines HTTP hinter eigenem Reverse Proxy
docker-compose.yml           Basisstack mit HTTP-Port
docker-compose.override.yml  HTTPS-Port-Mapping für internal/public
.github/workflows/           CI
```
