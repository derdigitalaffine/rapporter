# Fahrzeuge und Fahrtenbuch

## Nutzung

Das Premiummodul steht erwachsenen Familienmitgliedern unter **Mehr → Fahrzeuge und Fahrtenbuch** zur Verfügung. Eine Premium-/VIP-Freischaltung oder die einzelne Capability `vehicles` ist erforderlich. Vor dem bestehenden kommerziellen Cutover gilt wie bei den anderen Premiumfunktionen VIP für Bestandsfamilien. Das Modul fügt keinen primären Navigationstab hinzu. **Hinzufügen → Fahrzeug hinzufügen** nutzt denselben Stammdateneditor.

1. Fahrzeug anlegen: Name, Kennzeichen, Kilometerstand, Antrieb. Hersteller, Modell, FIN, Erstzulassung und Notizen sind unter Weitere Details erreichbar. Bestehende Fahrzeuge lassen sich bearbeiten oder archivieren; während einer offenen Fahrt ist Archivieren gesperrt.
2. Tankvorgang / Laden erfassen: Datum, Kilometerstand, Menge (Liter oder kWh), Gesamtbetrag; optional Währung, Station und Volltank-/Vollladeangabe. Tankdaten werden mit Erwachsenen derselben Familie geteilt. Ein Tankvorgang erzeugt keine zusätzliche Familienausgabe und verändert keine Abrechnungssalden.
3. Vor dem Losfahren den Kilometerstand prüfen, Standortaufzeichnung bewusst auswählen und **Fahrt starten**. Eine neue aufgezeichnete Fahrt startet absichtlich als **Noch zuordnen**. Die fachliche Klassifizierung wird nicht während der Fahrt erzwungen. Bedienung nur im Stand bzw. durch Beifahrer.
4. GPS lässt sich pausieren und wieder fortsetzen. Die Fahrt bleibt dabei offen. **Fahrt beenden** mit dem tatsächlichen Endkilometerstand schließt sie ab. GPS-Strecke ist eine Näherung; die Kilometerzähler-Strecke wird separat angezeigt.
5. Abgeschlossene Fahrten erscheinen in der Review-Inbox. Sie werden als `Privat`, `Arbeitsweg` oder `Dienstlich` zugeordnet. Dienstliche Fahrten benötigen Ziel, Geschäftspartner/Kunde und einen konkreten geschäftlichen Zweck; Notiz und Umweg-/Abweichungsbegründung sind optional. Eigene frühere Ziele, Partner und Zwecke können als Vorschläge erscheinen. Inhalte anderer Fahrer werden dafür nie verwendet.
6. Für neue aufgezeichnete Fahrten setzt Rapporter eine Review-Frist von sieben Tagen als konservative Produktregel. Die erste Zuordnung innerhalb der Frist kann ohne Änderungsgrund erfolgen. Nach Fristablauf sowie für spätere Änderungen ist ein Grund erforderlich. Jede nachträgliche Korrektur erhält eine fachliche Revision mit Zeitpunkt, Actor sowie Vorher-/Nachher-Snapshot. Das ist eine Nachvollziehbarkeitsfunktion, keine rechtliche Anerkennungszusage.
7. Fehlt eine Fahrt, kann sie mit tatsächlichem Zeitraum und Kilometerständen nachgetragen werden. Ein manueller Nachtrag ist dauerhaft als `manual` erkennbar und benötigt einen Grund; der technische Erstellzeitpunkt wird nicht auf den Fahrtzeitpunkt zurückdatiert.
8. Abgeschlossene Fahrten werden nicht mehr hart gelöscht. **Fahrt stornieren** behält den Datensatz und erzeugt eine Revision mit Begründung. GPS-Punkte einer stornierten Fahrt bleiben fahrerprivat und werden nicht exportiert.
9. Auswertung und Export lassen sich nach Zeitraum, Fahrtart und Review-Status filtern. Die UI zeigt Gesamtstrecke, dienstliche/private Strecken und offene Zuordnungen. CSV, PDF und CSV-AuditLog werden serverseitig über alle passenden Fahrten erzeugt; die 500-Zeilen-Grenze der Bildschirmhistorie begrenzt den Export nicht.

## Revisionshistorie und Altbestand

`JourneyRevision` ist eine fachliche, fahrerprivate Änderungshistorie innerhalb der bestehenden `vehicles`-Domain. Sie speichert für Nachtrag, Zuordnung, Korrektur und Storno den Änderungsgrund sowie die erlaubten Vorher-/Nachher-Fahrtdaten. GPS-Punkte gehören bewusst nicht in diese Snapshots. Diese Historie ist keine zweite generische Plattform-Audit-Lösung; Security-/Admin-/Usage-Audit bleibt beim zentralen Telemetrie-/Audit-Core aus #204, der keine privaten Fahrtenbuchinhalte erhält.

Fahrten, die bereits vor `vehicles.0002` existierten, werden als **Altbestand / Legacy** markiert. Sie bleiben vollständig nutzbar, werden aber nicht rückwirkend so dargestellt, als sei ihre Entstehung bereits durch die neue Revisionshistorie abgesichert gewesen. Neue Fahrten und Nachträge haben `legacy_record=false`.

## Privatsphäre und Grenzen

Fahrten, Zweck, Ziel, Geschäftspartner, Notizen, Revisionshistorie und GPS-Routen sind ausschließlich für die aufzeichnende Person zugänglich, auch gegenüber anderen Familien-Ownern. Stammdaten und Tankvorgänge sind innerhalb der Familie für Erwachsene zugänglich. Familienstatus, Membership, Rollen und Premiumrechte werden auf jedem API-, Export- und Kartenabruf erneut geprüft. Kein Standort- oder Fahrtenbuchinhalt wird in Produkttelemetrie, Pinnwand oder Heute projiziert.

Standorte werden erst nach Start/Fortsetzen gesammelt. Beim Verlassen des Moduls endet die GPS-Beobachtung, die Fahrt bleibt serverseitig offen. Nach Neuladen/Zurückkehren wird die offene Fahrt wieder angeboten; GPS startet erst nach erneuter bewusster Auswahl und **Aufzeichnung fortsetzen**. Das ist Browser-/PWA-Tracking im Vordergrund, kein nativer Hintergrunddienst: Bildschirmsperre, Energiesparen und App-Wechsel können Lücken verursachen.

GPS-Punkte warten bei Netzwerkfehlern im `sessionStorage` dieses Tabs, getrennt nach Nutzer, Familie und Fahrt. Neuladen desselben Tabs erhält den Puffer; Tab-Schließen kann noch nicht übertragene Punkte verlieren. Abmelden/Session-Ablauf löscht die lokalen GPS-Puffer. Der Server behält bereits übertragene Punkte. Der Puffer umfasst maximal 1000 Punkte; danach pausiert die Aufnahme. Pro Fahrt maximal 20.000 Punkte, GPS-Abtastung frühestens alle fünf Sekunden, Übertragung höchstens 100 Punkte je Request. Ungenaue Werte über 100 m und unplausible GPS-Sprünge werden verworfen/abgelehnt. Keine ergänzte Straßenroute oder erfundenen Punkte. Bei Übertragungsfehlern zunächst erneut versuchen; Stopp überträgt ausstehende Punkte vor dem Abschluss. Dieselbe Fahrt nur in einem Tab aufzeichnen.

Ein Startrequest, Tankrequest und GPS-Punkt haben stabile Wiederholungsschlüssel. Auch manuelle Nachträge besitzen einen stabilen Request-Key. Eine offene Fahrt pro Person und pro Fahrzeug ist zusätzlich in der Datenbank abgesichert. GPS-Punkte sind fortlaufend; Wiederholungen sind nur bei identischem Inhalt erlaubt. Stopp wiederholt keinen Abschluss und überschreibt keinen bereits gespeicherten Endstand.

### Steuerliche Einordnung

Rapporter unterstützt die persönliche, nachvollziehbare Fahrtenbuch-Dokumentation. Es gibt **keine Zusage** einer steuerrechtlichen Anerkennung, GoBD-Zertifizierung, Finanzamt-Garantie oder technischen Manipulationssicherheit. Insbesondere ist die Sieben-Tage-Review-Frist keine pauschale Compliance-Garantie: die entsprechende Verwaltungsregel für eine nachträgliche Ergänzung innerhalb von bis zu sieben Kalendertagen bezieht sich auf vollständig automatisch erfasste Fahrten. Das bestehende Rapporter-Tracking wird bewusst per Browser/PWA gestartet und gestoppt und ist kein garantiertes Hintergrund-Tracking.

Produktleitplanken orientieren sich an den veröffentlichten Anforderungen des BMF sowie der BFH-Rechtsprechung: elektronische Aufzeichnungen müssen die erforderlichen Fahrtdaten enthalten und nachträgliche Änderungen technisch ausschließen oder nachvollziehbar dokumentieren; für betriebliche Fahrten gehören insbesondere Ziel, Geschäftspartner und konkreter Zweck zu den relevanten Angaben. Die konkrete steuerliche Eignung eines individuellen Fahrtenbuchs ist mit Steuerberatung bzw. zuständiger Finanzverwaltung zu klären.

Referenzen:
- BMF, Lohnsteuer-Handbuch 2026, Hinweise zum elektronischen Fahrtenbuch und zur nachträglichen Ergänzung.
- BFH, Beschluss vom 12.01.2024 – VI B 37/23, Anforderungen an geschlossene Form und erkennbare nachträgliche Änderungen.
- BMF, Einkommensteuer-Hinweise: Mindestangaben bei betrieblichen Fahrten.

## OpenStreetMap und Betrieb

MapLibre GL JS wird als versionierte npm-Abhängigkeit gebündelt und erst beim Öffnen der Karte geladen. Standardmäßig kommt die OpenStreetMap-Rasterkarte von `https://tile.openstreetmap.org/{z}/{x}/{y}.png` zum Einsatz. **Kein Account oder API-Schlüssel erforderlich.** Sichtbare Attribution verlinkt die OSM-Copyrightseite und bleibt ohne zusätzlichen Toggle sichtbar.

Die Kacheln werden direkt vom Browser abgerufen. Der Browser respektiert die normalen HTTP-Cache-/Expiry-/ETag-Header; es werden keine `no-cache`-Header und keine FamilyOS-Credentials an den Anbieter gesendet. Nur für Tile-Requests gilt `referrerPolicy: origin`: OSM erhält die App-Adresse, keine Family-/Vehicle-/Journey-Queryparameter. Die globale Referrer-Policy bleibt unverändert. OSM sieht außerdem die Client-IP und den sichtbaren Kartenausschnitt. Der Fahrtzweck und die vollständigen GPS-Routendaten werden nicht übermittelt: die Route wird lokal als GeoJSON-Overlay gezeichnet. Karten werden nur nach **Karte anzeigen** geladen, nicht beim Öffnen des Fahrtenbuchs. Keine Offline-/Bulk-Downloads, keine Hintergrund-Prefetch-Jobs.

Die [OSM Tile Usage Policy](https://operations.osmfoundation.org/policies/tiles/) gilt für diesen Community-Dienst. Der Dienst bietet keine garantierte Verfügbarkeit. Bei Fehlern bleibt die Route auf neutraler Kartenbasis bzw. mit Hinweis verfügbar; Fahrzeugverwaltung und GPS/Fahrtenbuch sind davon unabhängig. Für größeren Betrieb oder eigene Verfügbarkeitsanforderungen kann eine eigene OSM-Kachelinfrastruktur genutzt werden.

`VEHICLES_OSM_TILE_URL` ist optional und standardmäßig auf den OSM-Endpoint gesetzt. Ein eigener Dienst im selben Origin kann als `/maptiles/{z}/{x}/{y}.png` konfiguriert werden. Die drei Platzhalter sind erforderlich; fremde Hosts, HTTP-Drittanbieter, URL-Credentials, Querytokens und Fragmente werden abgelehnt. Die Variable ist öffentlich und darf keine Geheimnisse enthalten. Die alte `VEHICLES_GEOFABRIK_TILE_URL` wird nicht mehr verwendet und kann aus bestehenden Deployment-Umgebungen entfernt werden. Es gibt keinen Geofabrik-Tile-Proxy mehr.

Alle Caddyvarianten erlauben OSM-Kacheln gezielt in `connect-src`/`img-src`; sonstige externe Quellen bleiben gesperrt. MapLibre verwendet einen gebündelten Worker im selben Origin, sodass `worker-src self` erhalten bleibt. `img-src blob:` erlaubt die lokale Bilddecodierung der Rasterkacheln, keine Scriptausführung. `Permissions-Policy: geolocation=(self)` erlaubt die Standortfunktion ausschließlich der eigenen Anwendung. Die explizite Aufzeichnungswahl und die Standortfreigabe des Browsers bleiben nötig; Kamera/Mikrofon werden weiterhin nicht aktiviert.

Die privaten Fahrzeuge-/Fahrt-APIs einschließlich Kartenkonfiguration und Reports bleiben `private, no-store`. Der Service Worker behandelt Drittanbieterrequests nicht und legt keine OSM-Kacheln oder GPS-Punkte in seinem Offline-Appcache ab.

## API und Migration

- `GET/POST /api/vehicles/?family=<uuid>` und `PATCH /api/vehicles/<uuid>/`
- `GET/POST /api/vehicles/<uuid>/fuel/`
- `GET/POST /api/vehicles/<uuid>/journeys/` – GET unterstützt `from`, `to`, `kind`, `review`; POST startet eine aufgezeichnete Fahrt
- `POST /api/vehicles/<uuid>/journeys/manual/` – fehlende Fahrt mit Grund nachtragen
- `GET /api/vehicles/<uuid>/journey-suggestions/` – ausschließlich eigene frühere Ziel-/Partner-/Zweckwerte
- `GET /api/vehicles/<uuid>/journey-report/` – Filter wie oben; `format=json|csv|pdf|audit`
- `GET /api/vehicles/active/?family=<uuid>`
- `GET/POST/DELETE /api/vehicle-journeys/<uuid>/` – POST beendet; DELETE liefert für abgeschlossene Fahrten `revision_required` statt Daten zu entfernen
- `POST /api/vehicle-journeys/<uuid>/points/`
- `POST /api/vehicle-journeys/<uuid>/classify/`
- `POST /api/vehicle-journeys/<uuid>/correct/`
- `POST /api/vehicle-journeys/<uuid>/void/`
- `GET /api/vehicle-journeys/<uuid>/revisions/`
- `GET /api/vehicles/map-config/?family=<uuid>` liefert die öffentliche Kartenkonfiguration nach Premium-/Family-/Adult-Prüfung

`vehicles.0001` bleibt die additive Basismigration. `vehicles.0002_professional_logbook` erweitert `Journey`, legt die fachliche Revisionstabelle und Report-Indizes an und markiert nur den bereits vorhandenen Fahrtenbestand als Legacy. Neue Datensätze verwenden danach den normalen Default `legacy_record=false`. Die Migration löscht keine bestehenden Fahrten oder GPS-Punkte. `entitlements.0002` bleibt unverändert; Capability- und Cutover-/Grant-Modell werden nicht dupliziert.

Auf bestehendem Datenbestand `python manage.py migrate` ausführen. Anwendungsrollback lässt Daten bestehen; ein Schema-Downgrade von `vehicles.0002` entfernt die neuen Metadaten/Revisionszeilen und gehört deshalb nur in eine bewusst geplante Wiederherstellung mit Backup. Es gibt keinen irreversiblen Inhalts-Backfill und keine automatische Umetikettierung bestehender Fahrten zu „compliant“.

DE/EN-Copy, vorhandene FormShell/Sections/Fields/Actions/ErrorSummary, gemeinsame Bestätigungsdialoge sowie Premium-/Create-Infrastruktur werden wiederverwendet. Es entstehen keine zweite Expense-, Calendar-, Task-, Document- oder generische Audit-Domain.
