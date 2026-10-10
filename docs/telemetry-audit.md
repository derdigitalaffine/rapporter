# Telemetrie- und Audit-Core

Dieser Core ist die datensparsame Grundlage für #204. Er ist bewusst **kein Clickstream** und enthält keine API, mit der normale Familiennutzer globale Telemetrie- oder Auditdaten lesen können.

## Datenklassen

### `AuditEvent`

Append-orientierte Security-/Admin-Ereignisse. Zulässige `event_key`- und Metadata-Felder stehen ausschließlich in `telemetry.catalog`.

Nicht erlaubt sind freie Request-/Response-Bodies, Passwörter, JWTs, Cookies, Reset-/Invite-Tokens, WebAuthn-Challenges/Credentials, SMTP-Secrets oder Fachinhalte aus Nachrichten, Tasks, Shopping, Kalender, Dokumenten/OCR, Baby/Pregnancy/Pet/Health.

Unbekannte Event-Keys, Metadata-Felder und freie Reason-Werte werden abgewiesen. Für unbekannte Login-Adressen ist nur ein serverseitig erzeugter 64-stelliger keyed Hash als `identifier_hash` vorgesehen; eine Klartext-Adresse ist kein zulässiges Audit-Feld.

`AuditEvent.save()` erlaubt nach dem Insert keine normalen Updates. Retention darf alte Events löschen; das ist kein Versprechen kryptographischer Unveränderbarkeit gegenüber DB-Administratoren.

### `UsageEvent`

Usage Events besitzen **kein freies JSON-Metadata-Feld**. Der erste Katalog enthält nur:

- `activity.foreground`: echte, authentifizierte Vordergrundaktivität,
- `module.used`: Nutzung eines stabil allow-gelisteten Modul-Keys.

Beide Events benötigen eine aktive Family-Membership. Sie werden pro User, Family, Event, Modul und UTC-Stunde dedupliziert. Token-Refresh, Healthchecks, Scheduler oder Hintergrundpolling sollen diese Services nicht aufrufen.

### `DailyRollup`

Rollups sind persistente UTC-Tagesaggregate. Der aktuelle Core definiert:

- `usage.active_users`: eindeutige Nutzer mit `activity.foreground`, global und pro Family,
- `usage.active_families`: eindeutige aktive Families global,
- `usage.module_users`: eindeutige Modulnutzer global und pro Family,
- `audit.event_count`: Anzahl allow-gelisteter Audit-Events nach Event-Key und Outcome.

`recompute_daily_rollups(day)` löscht und erzeugt nur den angegebenen Tag innerhalb einer Transaktion neu. Wiederholte Ausführung ist damit deterministisch/idempotent.

## Retention

Defaults:

- `TELEMETRY_USAGE_RETENTION_DAYS=60`
- `TELEMETRY_AUDIT_RETENTION_DAYS=180`

`python manage.py prune_telemetry` löscht abgelaufene Raw Events in begrenzten Batches. `DailyRollup` wird dabei nicht gelöscht. Family-spezifische Usage-/Rollup-Daten werden bei Family-Löschung über FK-Cascade entfernt; Audit-Referenzen auf User/Family werden auf `NULL` gesetzt, damit zulässige Security-Historie ohne Personen-/Tenant-FK fortbestehen kann.

## Jobs

```bash
python manage.py rollup_telemetry --date 2026-10-10
python manage.py prune_telemetry --batch-size 1000
```

Ohne `--date` berechnet `rollup_telemetry` den vorherigen UTC-Tag. Scheduling/Heartbeat/Operations-Surface wird in einem Anschluss-Slice ergänzt; dieser Core verändert den bestehenden Docker-Scheduler noch nicht.

## Integrationsvertrag für Fachcode

Fachcode soll bevorzugt `try_record_audit_event()` bzw. `try_record_usage_event()` verwenden. Diese Wrapper loggen nur Event-Key + Fehlerklasse und lassen Telemetrie-Ausfälle die fachliche Aktion nicht beschädigen. Für Tests und explizite Validierung existieren die strikten `record_*`-Varianten.

Auth-/Session-/Passkey-Hooks werden erst nach Integration von #196/#202 rebased ergänzt, damit die aktiven Identity-/Session-Branches nicht parallel überschrieben werden. Superadmin-/Domain-Aktionen werden anschließend als kleine Hooks auf denselben Katalog verdrahtet; es entsteht keine zweite Audit-Datenwelt.
