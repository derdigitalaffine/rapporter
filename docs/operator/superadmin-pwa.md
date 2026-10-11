# Superadmin PWA

Der Superadmin-Bereich wird als eigenständige, installierbare Web-App unter `/superadmin/` ausgeliefert. Die Trennung betrifft die Bedienoberfläche und den Session-Namespace; Identity, Sessions, Abuse Protection, Mail, Audit und Tenant-Domains bleiben kanonische FamilyOS-Plattformdienste.

## Installation und Anmeldung

1. FamilyOS normal unter `/` öffnen und bei Bedarf als Home-Screen-App installieren.
2. `/superadmin/` separat in Safari öffnen und als eigene Home-Screen-App installieren.
3. In der Admin-App mit einem Superadmin-Konto anmelden.

Das Manifest der Admin-App besitzt eine eigene App-ID, `start_url` und `scope` unter `/superadmin/`. Die Admin-App registriert einen eigenen Service Worker für genau diesen Scope. Root- und Admin-Service-Worker löschen ausschließlich ihre jeweils eigenen versionierten Caches.

Die Admin-PWA verwendet eigene HttpOnly-Cookies für Access und Refresh. Diese Cookies sind auf `/api/superadmin/` begrenzt. Normale FamilyOS-Cookies authentifizieren keine Superadmin-API und ein Admin-Logout widerruft nur die Admin-Sitzung. Beide Session-Arten verwenden weiterhin dasselbe serverseitige `AuthSession`-Modell, dieselben Revocation-/Rotation-Verträge und dieselbe Abuse Protection.

## Informationsarchitektur

Die erste Cockpit-Scheibe bildet die langfristige Struktur aus #205 ab, ohne nicht vorhandene Analytics vorzutäuschen:

- **Übersicht** – belastbare operative Counts und Aufmerksamkeitspunkte
- **Nutzer** – Identity, E-Mail-Änderung über Verification und Password Recovery
- **Familien** – Tenant-Anlage, Owner-Invite, Sperren/Reaktivieren
- **E-Mail** – SMTP-Konfiguration, Testversand und redigiertes Mailjournal
- **Betrieb** – vorhandene Mail-Health-Metriken und Fehlerklassen
- **Sicherheit** – aktive Admin-Sitzungen und Fresh-Session-Status

DAU/WAU/MAU, Retention, Funnel und weitere Analytics aus #205 werden erst ergänzt, wenn die dafür vorgesehenen #204-Rollups und APIs stabil vorhanden sind. Es werden keine privaten Familieninhalte, Mailbodies, Tokens, Passwörter, Passkey-Credentials oder vollständigen Empfängerlisten als Ersatzmetriken verwendet.

## Sensitive Aktionen

SMTP-Schreibzugriffe, Tenant-Status, Owner-Einladungen, E-Mail-Änderungen und Recovery verwenden weiterhin die vorhandene Fresh-Reauth- und `superadmin.sensitive_action`-Policy. Die Passwort-Reauthentifizierung der Admin-PWA erneuert nur den Access-Cookie der Admin-Sitzung.

## Offline- und Cache-Grenzen

Der Admin-Service-Worker cached nur die statische App-Shell und gebaute Assets. `/api/*` und `/admin/*` werden nie in den Admin-Cache geschrieben. Dadurch liegen keine Superadmin-API-Antworten mit Nutzer-, Mail- oder Betriebsmetadaten im Offline-Cache.

## Rollback

Diese Änderung benötigt keine Datenbankmigration. Ein Rollback entfernt den separaten Frontend-Einstieg und die dedizierten Admin-Auth-Routen/Cookies. Die zugrunde liegenden Superadmin-APIs, Identity-/Session-Modelle und fachlichen Daten bleiben unverändert.
