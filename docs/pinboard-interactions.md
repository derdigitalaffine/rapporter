# Pinnwand-Interaktionen

Kommentare und Reaktionen gehören in FamilyOS ausschließlich zum jeweiligen **Pin auf der Pinnwand**. Sie verändern weder das verknüpfte Quellobjekt noch dessen Freigaben und werden nicht für Ranking, Priorisierung oder Engagement-Scores verwendet.

## Reaktionen

Pro Familienmitglied und Pin bzw. Kommentar gibt es genau eine aktive Reaktion. Zur Auswahl stehen bewusst nur `Passt`, `Herz`, `Freude`, `Feiern` und `Gesehen`. Eine andere Reaktion ersetzt die bisherige; ein erneuter Tap auf die eigene sichtbare Reaktion entfernt sie. Die API speichert dafür immer den gewünschten Zustand (`key` oder `null`) per idempotentem `PUT`, damit Retries keine unbeabsichtigten Toggles erzeugen.

## Kommentare und Erwähnungen

Der Kommentarstrom ist flach und chronologisch; Antworten setzen nur den Fokus und eine `@Name`-Erwähnung. Kommentare sind Plain Text. HTTP-/HTTPS-Links werden als sichere Links dargestellt; HTML, Attachments und Rich Text gehören nicht in Kommentare.

Neue Kommentare tragen eine vom Client erzeugte `client_id`. Ein Retry mit derselben ID und demselben Autor erzeugt keinen zweiten Kommentar. Autoren können ihre Kommentare bearbeiten und löschen. Löschen ist ein Tombstone: Text, Mentions und Reaktionen werden entfernt, die stabile Kommentar-ID bleibt bestehen. Der Family Owner darf moderierend löschen; das Audit protokolliert dabei nur die technische Kommentar-ID, niemals den Kommentartext.

`@`-Vorschläge enthalten nur aktuelle aktive Memberships, die den Pin **und eine eventuell verknüpfte Quelle** im Moment der Interaktion effektiv sehen dürfen. Eine Erwähnung erweitert niemals Rechte.

## Sichtbarkeit und Datenschutz

Für Lesen, Schreiben, Counts, Reactions, Mentions und Activity gilt immer derselbe zentrale Vertrag:

`effektiver Zugriff = Pin-Sichtbarkeit ∩ Quellobjekt-Sichtbarkeit`

Wird ein Source-Zugriff entzogen, sind Thread und Interaction-Counts für die betroffene Person sofort nicht mehr zugänglich. Derselbe Zugriff wird direkt vor Notification-Fan-out erneut berechnet, damit ein früherer Kommentator nach Rechteentzug keine weitere Pinnwand-Aktivität erhält.

Die Board-Liste enthält nur kompakte Aggregationen (`comment_count`, ungelesen, Reaktionssummen, eigene Reaktion, Mute-Zustand), niemals Kommentartexte. Benachrichtigungen verwenden ebenfalls generische Pinnwand-Texte und enthalten weder Pin-Beschriftungen noch Source-Titel oder Kommentartext.

Reaktionen erzeugen höchstens In-App-Aktivität für den betroffenen Autor und keine Push-Flut. Kommentare und direkte Erwähnungen verwenden die bestehende zentrale Notification-Infrastruktur. Ein stummgeschalteter Thread unterdrückt normale Kommentaraktivität; eine direkte Erwähnung darf weiterhin im In-App-Center erscheinen.

## Bedienung und Barrierefreiheit

Die wiederverwendbare `PinInteractionBar` sitzt ruhig am Kartenfuß. Bereits sichtbare Reaktionschips können mit einem Tap bedient werden; `Reagieren` öffnet einen kleinen Picker. `Kommentieren` öffnet ein modales Thread-Sheet und fokussiert das Eingabefeld.

Das Sheet sperrt den Hintergrundscroll, hält den Tastaturfokus im Dialog, schließt mit `Escape` und gibt den Fokus danach an den auslösenden Kommentar-Button zurück. Interaktionsziele sind mindestens 44 px groß und besitzen textliche Accessible Names; Emoji sind nie die einzige Bedeutung. Die mobile Abnahme erfolgt mindestens bei 390 × 844 ohne horizontalen Overflow sowie in Deutsch und Englisch.

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
