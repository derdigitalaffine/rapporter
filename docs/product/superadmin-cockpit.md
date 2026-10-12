# Integriertes Superadmin-Cockpit

Parent: #205 · Roadmap/Gate B: #223 · Mess- und Auditvertrag: #204.

Die getrennte Admin-PWA integriert die vorhandenen kanonischen APIs in derselben Navigation. FamilyOS-Sessions oder Familienrollen öffnen diese Oberfläche nicht. Die Admin-Session, Fresh-Reauth, sensitive CRUD-/Recovery-/Tenant-Aktionen und serverseitigen ACLs bleiben unverändert zuständig.

| Bereich | Kanonische Quelle | Geliefertes Verhalten |
|---|---|---|
| Übersicht | `/superadmin/analytics/overview/` | Globale Totals, Aktivität im gewählten Zeitraum, Vergleich und zugängliche Tageswert-Tabelle; keine Totals aus einer Nutzerseite |
| Onboarding | gleiche Overview-Quelle | Membership-/Owner-Invite-Funnel, SMTP-Annahme ausdrücklich ohne Lesebestätigung, versionierte Aktivierung, Day-N-Retention mit Nenner/Small-n-Unterdrückung und Beobachtungsgrenze |
| Nutzer | paginiertes `/superadmin/users/`, bestehendes User-Detail | Server-Suche, Status, Sortierung, 25er-Paging, Security-/Membership-/Invite-/Audit-Drill-down; `section=users` bleibt Recovery-Default, `mode=crud` zeigt die kanonische Benutzerverwaltung innerhalb derselben Shell |
| Familien | paginierte bestehende Families-API und Family-Detail | Server-Suche, Status/Sortierung/Paging, operative Details; bestehendes Tenant-Anlegen, Owner-Einladen und Sperren bleiben erhalten |
| Sicherheit | `/superadmin/security/summary/` und bestehende eigene Admin-Sessionliste | Globale Auth-/Passkey-/Rate-Limit-Kennzahlen getrennt von den ausschließlich eigenen Admin-Sessions |
| Zustellung | `/superadmin/delivery/summary/` plus SMTP/Mail-Health/Journal | Mail/Push-Aggregate, Null-Nenner ohne erfundene Prozentzahl, bestehende reauth-geschützte SMTP-Aktionen |
| Betrieb | `/superadmin/operations/health/` plus bestehender Queue-Health | Lesbare Zustände/Ursachen; Worker ohne verlässliche Heartbeat-Quelle ausdrücklich unbekannt |
| Audit | `/superadmin/audit/` | Validierte strukturelle Filter, Paging, redigierte Event-Metadaten und gefilterter serverseitig auditierter CSV-Export; kein Raw-JSON-Dump |

Zeiträume 24h, 7d, 30d, 90d und 365d stammen aus dem bestehenden API-Vertrag. UTC wird ausdrücklich angezeigt, Datumformatierung verwendet diese Zone und die gewählte Sprache. Der Zeitraum und strukturelle Filter sind bookmarkbar. Freitext mit möglichen E-Mail-Adressen bleibt im aktuellen UI-Speicher und wird nicht in die Browser-URL kopiert. Zahlen/Nullwerte und Prozent-/Sekundeneinheiten bleiben unterscheidbar.

Neue Kennzahlen-/Navigation-/Filter-/Status-/Fehlertexte sind für DE/EN/FR/NL/TH vorhanden. Die bestehende sensible Schreiboberfläche wird hier integriert, nicht als neuer Form-/Identity-Core nachgebaut. Häufige Navigation/Suche zuerst, technische Definitionen und Detailmetadaten unter progressiven Details. Fehler und Retry bleiben pro Datenquelle bedienbar; bekannte Daten bleiben während derselben autorisierten Refresh-Abfrage sichtbar. Keine Offline-Schreibwarteschlange, keine automatischen administrativen Aktionen, kein sekündliches Polling.

## Explizit offener Rest von #205

Diese integrierte Lieferung schließt den Backend-only-Gap des Cockpit-Gates. Sie erklärt den gesamten ursprünglichen Epic nicht für vollständig:

- #503: Gesamt-/Custom-Zeiträume, gemeinsame globale Familienstatus/Auth-/Locale-Filter, ergänzende definierte KPI-/Trendverträge.
- #504: Wochen-/Monatskohorten sowie dauerhafte historische Activity-/Activation-/Retention-Beobachtungsabdeckung über die Rohdaten-Retention hinaus. Activity und meaningful activation lesen ebenfalls Raw UsageEvent; Zeiträume oder Vergleiche vor der observation_cutoff sind sichtbar eingeschränkt und keine vollständige historische Erhebung.
- #505: kanonische Worker-Heartbeats, erklärbare Attention Queue und fehlende globale Session-/Passkey-/Push-/Digest-/Preference-KPIs.
- Billing bleibt bei #83. Matomo bleibt optionale, gesonderte Analytics-Berichterstattung und ersetzt nie kanonische Auth-/Invite-/Mail-/Retention-Kennzahlen.

Es wurden keine neuen Mikroendpunkte oder Domain-/Permission-Modelle eingeführt. Backend-Retention-Korrektur: nur vollständige mature Beobachtungsfenster zählen; purgierte Fenster sind niemals falsches Non-return/0 %. Rücknahme der UI erfolgt durch Revert der Frontend-Integration; die bestehenden APIs, kanonische CRUD-Verwaltung und sensible Admin-Aktionen bleiben verfügbar. Keine destruktive Migration.

## Validierung

Production-Build einschließlich fünfsprachiger Core-Guards. Bestehende Superadmin-E2Es behalten direkte E-Mail-Korrektur, Reset-Link/Kopie, SMTP-Reauth und Tenant-Aktionen auf ihren bisherigen Routen. Neue E2Es prüfen tatsächliche globale Totals vs. paginierte Directory-Abfragen, Status-/Sortier-/Paging-Requests, ID-Fallback mit Status, retrybare Details, isolierte Fehler, Null-/Small-n-/SMTP-/Unknown-Semantik, Filter/CSV, fünf Sprachen, Tastatur und 320/390/1024/1440 sowie 200-%-Layout. CI ist der Browser-Gate; lokal ist Chromium-Download im Arbeitsumfeld nicht verfügbar.
