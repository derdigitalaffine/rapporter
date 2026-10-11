# Karten & Tickets Core

`Karten & Tickets` erweitert die bestehende Bonuskarten-Domain additiv zu einem generischen Pass-Core. Die persistierte Django-Entität und die Route `/api/loyalty-cards/` bleiben aus Kompatibilitätsgründen bestehen; neue Fachlogik spricht von einem `PassItem` und verwendet `LoyaltyCard` als rückwärtskompatibles Persistenzmodell.

## Pass-Typen

Der Core kennt `loyalty_card`, `voucher`, `coupon`, `ticket` und `boarding_pass`. Bestehende Datensätze werden durch die additive Migration automatisch als `loyalty_card` behandelt. Barcode-Payload und `barcode_format` werden dabei nicht transformiert oder neu kodiert.

Beispiel für einen Gutschein:

```json
{
  "family": "<family-uuid>",
  "name": "10 € Gutschein",
  "pass_type": "voucher",
  "icon_key": "gift",
  "color_mode": "auto",
  "color": "#6750A4",
  "barcode_value": "VOUCHER-123",
  "barcode_format": "code128",
  "undo_window_minutes": 10,
  "shared_with_ids": ["<membership-uuid>"]
}
```

Die feste Registry ist über `GET /api/loyalty-cards/catalog/` verfügbar. Persistiert wird ausschließlich `icon_key`; freie CSS-/HTML-Klassen oder URL-basierte Icons sind kein Teil des Vertrags. Die Registry enthält mehr als 50 allgemeine, Einkaufs-, Event-, Reise-, Freizeit-, Mitgliedschafts- und Service-Symbole. `color_mode=auto` verwendet die serverseitig definierte Akzentfarbe des Icons. `color_mode=custom` verwendet eine validierte `#RRGGBB`-Farbe. Bestehende `logo`- und `color`-Werte bleiben lesbar und werden bei unveränderter Bearbeitung nicht migriert.

## Lifecycle und Undo

Ein Pass startet aktiv. `POST /api/loyalty-cards/{id}/redeem/` markiert einen sichtbaren Pass als verwendet, archiviert ihn und setzt `restore_until` auf `used_at + undo_window_minutes`. Das Zeitfenster ist pro Pass zwischen 1 und 1440 Minuten konfigurierbar; Standard sind 10 Minuten. Während dieser Frist stellt `POST /api/loyalty-cards/{id}/restore/` den Pass wieder her. Nach Ablauf antwortet der Server mit `409` und der Pass bleibt archiviert.

Ein manuelles Löschen über die bestehende `DELETE`-Route archiviert mit `archive_reason=manual` und eröffnet bewusst kein Undo-Fenster. Tickets und Boardingpässe mit `event_ends_at` werden beim nächsten autorisierten Pass-Lesezugriff automatisch mit `archive_reason=event_ended` archiviert; auch dafür gibt es kein UI-Restore. Dadurch ist die Restore-Policy allein anhand von serverseitigen Zeitstempeln und Gründen deterministisch und nicht von Client-Uhren abhängig.

## Berechtigungen und Sharing

Der Core führt **keine neue ACL** ein. Sichtbarkeit bleibt exakt an den bestehenden Bonuskartenvertrag gebunden: Ersteller, explizit freigegebene Familienmitglieder und Familien-Owner können einen Pass lesen. Nicht freigegebene Mitglieder und fremde Familien erhalten ihn weder in Listen/Details noch über den Offline-Sync.

Master-Daten und Freigaben dürfen weiterhin nur Ersteller oder Familien-Owner ändern. `redeem` ist dagegen eine Benutzungsaktion: ein Familienmitglied, das einen Pass aufgrund der bestehenden Freigabe sehen und an der Kasse verwenden darf, darf ihn auch als verwendet markieren. Ein entzogener Nutzer kann einen bereits archivierten Pass nicht wiederherstellen, weil die Restore-Route dieselbe Sichtbarkeits-ACL erneut erzwingt.

## Offline-Vertrag

Die PWA synchronisiert weiterhin ausschließlich `GET /api/loyalty-cards/sync/?family=...`. Diese Antwort enthält nur aktuell sichtbare, nicht archivierte Pässe. Der bestehende IndexedDB-Replacement-Sync entfernt dadurch entzogene, verwendete oder automatisch abgelaufene Pässe beim nächsten erfolgreichen Online-Sync. Barcode-Werte werden lokal aus Payload plus Symbologie gerendert; externe Rendering-, Logo- oder Barcode-Dienste sind nicht erforderlich.

## Datenschutz und Scope

Barcode-/QR-Werte werden weder für Branding noch Telemetrie verwendet. Die Icon-Registry enthält ausschließlich statische Produktdaten. OCR-/Dokumentimport, neue globale Sharing-Policies und eine Ersetzung des bestehenden Barcode-Scanners sind nicht Teil dieses Cores.

## Regressionen

Die Tests decken ab:

- Legacy-Bonuskarte behält `logo`, `color`, Barcode-Payload und Symbologie wertgleich.
- feste Icon-Registry mit mindestens 50 eindeutigen IDs; beliebige Icon-/Style-Werte werden abgewiesen.
- Typen und Auto-/Custom-Akzentfarben.
- bestehende Familien-/Sharing-ACL inklusive Cross-Family-Abschirmung.
- Redeem → Archiv → Undo innerhalb der Frist sowie serverseitiger Timeout danach.
- automatische Event-Archivierung ohne Restore.
- Offline-Sync entfernt archivierte oder entzogene Pässe.
- mobile Karten-/Ticket-Darstellung mit sichtbarem Typ-Hinweis ohne horizontalen Overflow.
