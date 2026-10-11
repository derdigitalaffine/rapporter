# Wichtige Schreiben verstehen

Issue #182 baut auf dem lokalen Document Core aus #179/#180 auf. Die Datei, OCR-/Textartefakte und `ExtractedField`-Provenienz bleiben dort kanonisch; der Correspondence-Core speichert ausschließlich die vom Nutzer geprüften bzw. korrigierten Fachwerte.

## Nutzerfluss

Der globale Create-Flow bietet **Wichtiges Schreiben**. Vor dem Upload wählt der Nutzer die Dokumentsichtbarkeit und kann anschließend ein Bild scannen oder PDF/Bild auswählen. Danach läuft derselbe Review-Editor:

1. Datei lokal im Document Core verarbeiten.
2. deterministische Vorschläge mit Confidence, Seite und Beleg anzeigen,
3. Werte manuell korrigieren,
4. Prüfung ausdrücklich bestätigen,
5. optional eine ausdrücklich bestätigte Folgeaktion auswählen oder das Schreiben nur ablegen.

Es gibt keinen LLM-/Cloud-Schritt und keine automatische Folgeaktion.

## Deterministische Extraktion

Der Review-Core verwendet vorhandene strukturierte `ExtractedField`-Werte und den bereits extrahierten Seitentext. Eng beschriftete lokale Regeln erkennen unter anderem Absender, Empfänger, Datum, Betreff, Akten-/Referenzzeichen, Betrag, IBAN, Frist und Kontakt. Handlungssätze werden nur bei klaren lokalen Signalwörtern wie *einreichen*, *zahlen*, *zurücksenden*, *unterschreiben*, *antworten*, *Widerspruch* oder *Termin* vorgeschlagen.

Fristen enthalten immer den Fundstellen-Text und, soweit vorhanden, die Seite. Handlungssätze sind `source_type="suggestion"` und `uncertain=true`; sie werden nie als sichere Dokumenttatsache dargestellt. Fehlt ein Signal, wird keine Handlung erfunden.

Der Kurzüberblick wird deterministisch aus manuell bestätigten Werten und eindeutigen Vorschlägen mit hoher Confidence zusammengesetzt. Unsichere Handlungsvorschläge werden erst nach manueller Bestätigung in den Überblick aufgenommen.

## Review-Daten

`CorrespondenceReview` ist 1:1 mit einem kanonischen `Document` verbunden und speichert nur das bereinigte Review-JSON sowie Reviewstatus/-zeitpunkt. Leserechte folgen vollständig der aktuellen Document-ACL; Änderungen benötigen `can_manage_document`. Fremde Familien und nicht sichtbare Dokumente liefern fail-closed `404`.

## Action Wizard

`POST /api/correspondence/<document>/actions/` verlangt immer `confirmed=true`.

Unterstützte Aktionen:

- `store_only`: nur Review abschließen,
- `task`: kanonische `Task`, Dokument-Backlink über `DocumentLink`,
- `event`: kanonischer `FamilyEvent`, Dokument-Backlink über `DocumentLink` und Payload,
- `shopping`: kanonisches `ShoppingItem` in einer bestehenden Liste; Backlink über den bestehenden `ContextLink`-Core,
- `expense`: kanonische `Expense` mit `receipt_document` und `DocumentLink`,
- `link`: Verknüpfung des Schreibens mit einem bestehenden Vertrag oder Haustier über `DocumentLink`.

Weitere Zieltypen werden erst angeboten, wenn dafür ein stabiler kanonischer Domain-Core existiert. Insbesondere wird für Schule in #182 kein Parallelmodell eingeführt.

### Privacy-Gate

Task, Termin, Einkaufsartikel und Ausgabe sind heute familienweite Projektionen. Deshalb blockiert der Server diese Aktionen mit `409 private_document_action`, wenn das Ursprungsdokument `private` oder `selected` ist. Damit können Betreff, Betrag oder Handlung eines privaten Schreibens nicht über einen anderen Domain-Core geleakt werden. `store_only` und ACL-geprüfte Verknüpfungen bleiben möglich.

Context Links erweitern keine Sichtbarkeit. Der Correspondence-App-Core registriert den Typ `document` und die Relation `correspondence.action` über die vorhandene `ContextRegistry`; die Registry-Implementierung selbst wird nicht dupliziert oder verändert.

## API

- `GET /api/correspondence/<document>/review/`
- `PATCH /api/correspondence/<document>/review/`
- `POST /api/correspondence/<document>/actions/`

## Migration und Rollback

`correspondence.0001_initial` legt nur `CorrespondenceReview` und seinen Familien-/Statusindex an. Es gibt keinen Daten-Backfill und keine Änderung am Document-Schema.

Beim Reverse-Migrate werden die Reviewzeilen entfernt. Kanonische Dokumente und bereits ausdrücklich bestätigte Zielobjekte bleiben erhalten; ihre bestehenden Document-/Context-Links bleiben eigenständige Fachmetadaten und werden nicht stillschweigend gelöscht.

## Tests

Die Backend-Tests decken insbesondere ab:

- deterministische Extraktion inklusive Beleg für Fristen,
- unsichere Kennzeichnung von Handlungsvorschlägen,
- persistente manuelle Korrektur und deterministischen Kurzüberblick,
- Bestätigungspflicht für Folgeaktionen,
- Privacy-Block für familienweite Projektionen,
- Document-/Context-Backlinks,
- Shopping nur in derselben Familie,
- fail-closed Zugriffe aus fremden Familien.
