# Pinnwand-Interaktionen

Kommentare und Reaktionen gehören in FamilyOS ausschließlich zum jeweiligen **Pin auf der Pinnwand**. Sie verändern weder das verknüpfte Quellobjekt noch dessen Freigaben und werden nicht für Ranking, Priorisierung oder Engagement-Scores verwendet.

## Reaktionen

Pro Familienmitglied und Pin bzw. Kommentar gibt es genau eine aktive Reaktion. Zur Auswahl stehen bewusst nur `Passt`, `Herz`, `Freude`, `Feiern` und `Gesehen`. Eine andere Reaktion ersetzt die bisherige; ein erneuter Tap auf die eigene sichtbare Reaktion entfernt sie. Die API speichert dafür immer den gewünschten Zustand (`key` oder `null`) per idempotentem `PUT`, damit Retries keine unbeabsichtigten Toggles erzeugen.

## Kommentare und Erwähnungen

Der Kommentarstrom ist flach und chronologisch; Antworten setzen nur den Fokus und eine `@Name`-Erwähnung. Kommentare sind Plain Text. HTTP-/HTTPS-Links werden als sichere Links dargestellt; HTML, Attachments und Rich Text gehören nicht in Kommentare.

Neue Kommentare tragen eine vom Client erzeugte `client_id`. Für einen unveränderten Entwurf bleibt diese ID auch nach einem mehrdeutigen Netz-/Serverfehler erhalten; erst bestätigter Erfolg oder ein bewusst veränderter Entwurf erhält einen neuen Request-Vertrag. Ein Retry mit derselben ID und demselben Autor erzeugt keinen zweiten Kommentar. Autoren können ihre Kommentare bearbeiten und löschen. Löschen ist ein Tombstone: Text, Mentions und Reaktionen werden entfernt, die stabile Kommentar-ID bleibt bestehen. Der Family Owner darf moderierend löschen; das Audit protokolliert dabei nur die technische Kommentar-ID, niemals den Kommentartext.

`@`-Vorschläge enthalten nur aktuelle aktive Memberships, die den Pin **und eine eventuell verknüpfte Quelle** im Moment der Interaktion effektiv sehen dürfen. Eine Erwähnung erweitert niemals Rechte.

## Sichtbarkeit und Datenschutz

Für Lesen, Schreiben, Counts, Reactions, Mentions und Activity gilt immer derselbe zentrale Vertrag:

`effektiver Zugriff = Pin-Sichtbarkeit ∩ Quellobjekt-Sichtbarkeit`

Wird ein Source-Zugriff entzogen, sind Thread und Interaction-Counts für die betroffene Person sofort nicht mehr zugänglich. Derselbe Zugriff wird direkt vor Notification-Fan-out erneut berechnet, damit ein früherer Kommentator nach Rechteentzug keine weitere Pinnwand-Aktivität erhält.

Die Board-Liste enthält nur kompakte Aggregationen (`comment_count`, ungelesen, Reaktionssummen, eigene Reaktion, Mute-Zustand), niemals Kommentartexte. Benachrichtigungen verwenden ebenfalls generische Pinnwand-Texte und enthalten weder Pin-Beschriftungen noch Source-Titel oder Kommentartext.

Reaktionen erzeugen höchstens In-App-Aktivität für den betroffenen Autor und keine Push-Flut. Kommentare und direkte Erwähnungen verwenden die bestehende zentrale Notification-Infrastruktur. Ein stummgeschalteter Thread unterdrückt normale Kommentaraktivität; eine direkte Erwähnung darf weiterhin im In-App-Center erscheinen.

## Bedienung und Barrierefreiheit

Die wiederverwendbare `PinInteractionBar` sitzt ruhig am Kartenfuß. Bereits sichtbare Reaktionschips können mit einem Tap bedient werden; `Reagieren` öffnet einen kleinen Picker. `Kommentieren` öffnet ein modales Thread-Sheet und fokussiert das Eingabefeld.

Das Sheet sperrt den Hintergrundscroll, hält den Tastaturfokus im Dialog, schließt mit `Escape` und gibt den Fokus danach an den auslösenden Kommentar-Button zurück. Interaktionsziele sind mindestens 44 px groß und besitzen textliche Accessible Names; Emoji sind nie die einzige Bedeutung. Der Composer erhält den Fokus sofort beim Öffnen, auch wenn Kommentar-/Mention-Reads noch laufen. Readfehler bieten einen Retry; gewöhnliche Netzwerkfehler bewahren den Entwurf. Bestätigter Rechteentzug entfernt Thread, Counts und private Entwürfe. Pin-/Familienwechsel, Logout und Unmount invalidieren laufende Requests, einschließlich verspäteter Fehler und Mutationsantworten. Bestätigungen bleiben beim gemeinsamen confirmAction-Host; die Thread-Fokusfalle greift nicht in diesen Dialog ein. Neue Copy und Datumsformate sind für DE/EN/FR/NL/TH vorhanden; Touchziele bleiben mindestens 44 × 44 px, einschließlich Reaktionschips. Die schmalen Sheet-Köpfe können umbrechen und Tabs kehren innerhalb des Sheets korrekt um.

## API

- `GET/POST /api/board/<pin>/comments/`
- `PATCH/DELETE /api/board/<pin>/comments/<comment>/`
- `PUT /api/board/<pin>/reaction/`
- `PUT /api/board/<pin>/comments/<comment>/reaction/`
- `GET /api/board/<pin>/mention-targets/`
- `POST /api/board/<pin>/seen/`
- `POST /api/board/<pin>/mute/`

Alle Endpunkte revalidieren die kanonische Pin-/Source-ACL serverseitig. Cross-Family- oder nicht sichtbare IDs liefern neutral keinen Zugriff.

Refs #203 #218 #220 #222 #223 #386

## Zentrale Abuse- und Zustellgrenzen

Interaktions-Mutationen nutzen die zentrale #206-Policy `pin.interaction` mit User-/Family-Burst-Grenzen (30/min, 300/h), keine lokale pro-View-Throttle-Welt. Die zentrale #203-Digest-Queue revalidiert effektive Pin-/Source-ACL, Mute-Zustand und gelöschte Kommentare beim tatsächlichen Flush erneut. Ein früherer Mention-/Kommentar-Empfänger erhält nach Rechteentzug keine später gepufferte sensible Aktivität.

## Explizit verbleibende Integration

Diese Lieferung implementiert den gemeinsamen Pin-Kontext und seinen Board-Consumer. Today besitzt derzeit noch keine entsprechenden Pin-Karten; die Today-Projection verwendet den gemeinsamen Interaction-Consumer erst im finalen #221-Cutover. Es gibt dafür keinen zweiten Thread-, API- oder Unread-State. #386 bleibt für diese benannte Abnahme offen; der aktuelle PR referenziert den Parent, statt den gesamten Today-/Board-Vertrag als vollständig zu schließen.

Bei einem bestätigten 403/404 entfernt der Board-Consumer die bisherige Karte einschließlich Beschriftung und Source-Preview sofort und lädt einmal den kanonischen Board-Reader nach. Nur dessen aktuell autorisierte/neutralisierte Projektion darf wieder erscheinen. Normale `authenticated:true`-Refresh-Ereignisse erhalten einen gültigen Entwurf; tatsächlicher Logout/Session-Verlust sowie die kanonischen App-Remounts bei Login und Familienwechsel verwerfen den alten Interaction-Kontext. Es wird keine eigene User-/Session-Authority aufgebaut.
