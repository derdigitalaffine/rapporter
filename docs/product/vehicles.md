# Fahrzeuge und Fahrtenbuch

## Nutzung

Das Premiummodul steht erwachsenen Familienmitgliedern unter **Mehr → Fahrzeuge und Fahrtenbuch** zur Verfügung. Eine Premium-/VIP-Freischaltung oder die einzelne Capability `vehicles` ist erforderlich. Vor dem bestehenden kommerziellen Cutover gilt wie bei den anderen Premiumfunktionen VIP für Bestandsfamilien. Das Modul fügt keinen primären Navigationstab hinzu. **Hinzufügen → Fahrzeug hinzufügen** nutzt denselben Stammdateneditor.

1. Fahrzeug anlegen: Name, Kennzeichen, Kilometerstand, Antrieb. Hersteller, Modell, FIN, Erstzulassung und Notizen sind unter Weitere Details erreichbar. Bestehende Fahrzeuge lassen sich bearbeiten oder archivieren; während einer offenen Fahrt ist Archivieren gesperrt.
2. Tankvorgang / Laden erfassen: Datum, Kilometerstand, Menge (Liter oder kWh), Gesamtbetrag; optional Währung, Station und Volltank-/Vollladeangabe. Tankdaten werden mit Erwachsenen derselben Familie geteilt. Ein Tankvorgang erzeugt keine zusätzliche Familienausgabe und verändert keine Abrechnungssalden.
3. Vor dem Losfahren Kilometerstand, Fahrtart und optional Zweck eingeben. Standortaufzeichnung bewusst auswählen und **Fahrt starten**. Die Standortfreigabe des Browsers bestätigen. Bedienung nur im Stand bzw. durch Beifahrer.
4. GPS lässt sich pausieren und wieder fortsetzen. Die Fahrt bleibt dabei offen. **Fahrt beenden** mit dem tatsächlichen Endkilometerstand schließt sie ab. GPS-Strecke ist eine Näherung; die Kilometerzähler-Strecke wird separat angezeigt.
5. Vergangene Fahrten öffnen, Route auf der Karte ansehen, als CSV exportieren oder mit Bestätigung löschen. Die letzten 500 Fahrten/Tankvorgänge werden angezeigt; der Export enthält diese geladenen Fahrten, keine GPS-Koordinaten.

## Privatsphäre und Grenzen

Fahrten, Zweck und GPS-Routen sind ausschließlich für die aufzeichnende Person zugänglich, auch gegenüber anderen Familien-Ownern. Stammdaten und Tankvorgänge sind innerhalb der Familie für Erwachsene zugänglich. Familienstatus, Membership, Rollen und Premiumrechte werden auf jedem API- und Kartenabruf erneut geprüft. Kein Standortinhalt wird in Produkttelemetrie, Pinnwand oder Heute projiziert.

Standorte werden erst nach Start/Fortsetzen gesammelt. Beim Verlassen des Moduls endet die GPS-Beobachtung, die Fahrt bleibt serverseitig offen. Nach Neuladen/Zurückkehren wird die offene Fahrt wieder angeboten; GPS startet erst nach erneuter bewusster Auswahl und **Aufzeichnung fortsetzen**. Das ist Browser-/PWA-Tracking im Vordergrund, kein nativer Hintergrunddienst: Bildschirmsperre, Energiesparen und App-Wechsel können Lücken verursachen.

GPS-Punkte warten bei Netzwerkfehlern im `sessionStorage` dieses Tabs, getrennt nach Nutzer, Familie und Fahrt. Neuladen desselben Tabs erhält den Puffer; Tab-Schließen kann noch nicht übertragene Punkte verlieren. Abmelden/Session-Ablauf löscht die lokalen GPS-Puffer. Der Server behält bereits übertragene Punkte. Der Puffer umfasst maximal 1000 Punkte; danach pausiert die Aufnahme. Pro Fahrt maximal 20.000 Punkte, GPS-Abtastung frühestens alle fünf Sekunden, Übertragung höchstens 100 Punkte je Request. Ungenaue Werte über 100 m und unplausible GPS-Sprünge werden verworfen/abgelehnt. Keine ergänzte Straßenroute oder erfundenen Punkte. Bei Übertragungsfehlern zunächst erneut versuchen; Stopp überträgt ausstehende Punkte vor dem Abschluss. Dieselbe Fahrt nur in einem Tab aufzeichnen.

Ein Startrequest, Tankrequest und GPS-Punkt haben stabile Wiederholungsschlüssel. Eine offene Fahrt pro Person und pro Fahrzeug ist zusätzlich in der Datenbank abgesichert. GPS-Punkte sind fortlaufend; Wiederholungen sind nur bei identischem Inhalt erlaubt. Stopp wiederholt keinen Abschluss und überschreibt keinen bereits gespeicherten Endstand.

Dieses Fahrtenbuch ist eine persönliche Dokumentation, keine Zusage eines steuerrechtlich anerkannten oder manipulationssicheren Fahrtenbuchs.

## OpenStreetMap und Betrieb

MapLibre GL JS wird als versionierte npm-Abhängigkeit gebündelt und erst beim Öffnen der Karte geladen. Standardmäßig kommt die OpenStreetMap-Rasterkarte von `https://tile.openstreetmap.org/{z}/{x}/{y}.png` zum Einsatz. **Kein Account oder API-Schlüssel erforderlich.** Sichtbare Attribution verlinkt die OSM-Copyrightseite und bleibt ohne zusätzlichen Toggle sichtbar.

Die Kacheln werden direkt vom Browser abgerufen. Der Browser respektiert die normalen HTTP-Cache-/Expiry-/ETag-Header; es werden keine `no-cache`-Header und keine FamilyOS-Credentials an den Anbieter gesendet. Nur für Tile-Requests gilt `referrerPolicy: origin`: OSM erhält die App-Adresse, keine Family-/Vehicle-/Journey-Queryparameter. Die globale Referrer-Policy bleibt unverändert. OSM sieht außerdem die Client-IP und den sichtbaren Kartenausschnitt. Der Fahrtzweck und die vollständigen GPS-Routendaten werden nicht übermittelt: die Route wird lokal als GeoJSON-Overlay gezeichnet. Karten werden nur nach **Karte anzeigen** geladen, nicht beim Öffnen des Fahrtenbuchs. Keine Offline-/Bulk-Downloads, keine Hintergrund-Prefetch-Jobs.

Die [OSM Tile Usage Policy](https://operations.osmfoundation.org/policies/tiles/) gilt für diesen Community-Dienst. Der Dienst bietet keine garantierte Verfügbarkeit. Bei Fehlern bleibt die Route auf neutraler Kartenbasis bzw. mit Hinweis verfügbar; Fahrzeugverwaltung und GPS/Fahrtenbuch sind davon unabhängig. Für größeren Betrieb oder eigene Verfügbarkeitsanforderungen kann eine eigene OSM-Kachelinfrastruktur genutzt werden.

`VEHICLES_OSM_TILE_URL` ist optional und standardmäßig auf den OSM-Endpoint gesetzt. Ein eigener Dienst im selben Origin kann als `/maptiles/{z}/{x}/{y}.png` konfiguriert werden. Die drei Platzhalter sind erforderlich; fremde Hosts, HTTP-Drittanbieter, URL-Credentials, Querytokens und Fragmente werden abgelehnt. Die Variable ist öffentlich und darf keine Geheimnisse enthalten. Die alte `VEHICLES_GEOFABRIK_TILE_URL` wird nicht mehr verwendet und kann aus bestehenden Deployment-Umgebungen entfernt werden. Es gibt keinen Geofabrik-Tile-Proxy mehr.

Alle Caddyvarianten erlauben OSM-Kacheln gezielt in `connect-src`/`img-src`; sonstige externe Quellen bleiben gesperrt. MapLibre verwendet einen gebündelten Worker im selben Origin, sodass `worker-src self` erhalten bleibt. `img-src blob:` erlaubt die lokale Bilddecodierung der Rasterkacheln, keine Scriptausführung. `Permissions-Policy: geolocation=(self)` erlaubt die Standortfunktion ausschließlich der eigenen Anwendung. Die explizite Aufzeichnungswahl und die Standortfreigabe des Browsers bleiben nötig; Kamera/Mikrofon werden weiterhin nicht aktiviert.

Die privaten Fahrzeuge-/Fahrt-APIs einschließlich Kartenkonfiguration bleiben `private, no-store`. Der Service Worker behandelt Drittanbieterrequests nicht und legt keine OSM-Kacheln oder GPS-Punkte in seinem Offline-Appcache ab.

## API und Migration

- `GET/POST /api/vehicles/?family=<uuid>` und `PATCH /api/vehicles/<uuid>/`
- `GET/POST /api/vehicles/<uuid>/fuel/`
- `GET/POST /api/vehicles/<uuid>/journeys/` (POST startet)
- `GET /api/vehicles/active/?family=<uuid>`
- `GET/POST/DELETE /api/vehicle-journeys/<uuid>/` (POST beendet; DELETE nur abgeschlossene eigene Fahrt)
- `POST /api/vehicle-journeys/<uuid>/points/`
- `GET /api/vehicles/map-config/?family=<uuid>` liefert die öffentliche Kartenkonfiguration nach Premium-/Family-/Adult-Prüfung

Additive Migration `vehicles.0001` legt ausschließlich neue Tabellen/Constraints an. `entitlements.0002` ergänzt den vorhandenen Capability-Katalog, keine Änderung des Cutover-/Grant-Modells. Auf bestehendem Datenbestand `python manage.py migrate` ausführen. Anwendungsrollback lässt Tabellen und Daten bestehen; Schema-Downgrade von `vehicles.0001` löscht Fahrzeug-/Tank-/Fahrtdaten und gehört nur in eine bewusst geplante Wiederherstellung mit Backup. Capability-Seed-Rückweg ist absichtlich ein No-op, damit bestehende Grant-Verweise erhalten bleiben. Keine irreversiblen Backfills.

DE/EN-Copy, vorhandene FormShell/Sections/Fields/Actions/ErrorSummary, gemeinsame Bestätigungsdialoge und Premium-/Create-Infrastruktur werden wiederverwendet. Es entstehen keine zweite Expense-, Calendar-, Task- oder Document-Domain.
