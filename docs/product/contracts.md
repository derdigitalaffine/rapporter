# Verträge

Issue #181 baut auf dem Document Core aus #179/#180 auf. Verträge sind eine eigene fachliche Entität; Dateien bleiben kanonische `Document`-Objekte und werden ausschließlich über `DocumentLink(domain_type="contract")` verknüpft.

## Nutzerfluss

Ein Vertrag kann vollständig ohne Datei angelegt und verwaltet werden. Der globale Create-Flow bietet `Vertrag` und führt über drei Einstiege in denselben Editor:

- manuell,
- Dokument scannen,
- PDF/Bild auswählen.

Bei einem Dokument verarbeitet der lokale Document-Core die Datei. `ExtractedField`-Werte dienen nur als Vorschläge im Editor. Der Nutzer prüft und speichert die Daten selbst. Für jeden unterstützten Vorschlag zeigt die UI Confidence, Seite, Belegtext und `source_type` an. Die vom Document-Core bereits gelieferten Vertrags-Keys (`contract.number`, `contract.start_date`, `contract.end_date`) werden direkt gemappt; weitere eng beschriftete Vertragsfelder werden lokal aus dem bereits extrahierten Seitentext vorgeschlagen, ohne eine zweite OCR- oder Cloud-Pipeline.

## Vertrag eingeben und bearbeiten

Der Editor führt durch die Abschnitte **Vertrag**, **Laufzeit**, **Kosten** und **Freigabe**. Auf dem Telefon stehen die Felder untereinander; auf größeren Bildschirmen stehen zusammengehörige Angaben wie Anbieter/Kategorie oder Betrag/Zahlungsintervall nebeneinander. Berechnete Fristen erscheinen direkt bei der Laufzeit und bleiben als Berechnung gekennzeichnet.

**Weitere Details** öffnet Vertrags- und Kundennummer, Verlängerungsregel, Status, Notizen und verknüpfte Dokumente. Diese Angaben bleiben beim Speichern erhalten, auch wenn der Bereich geschlossen ist. Erkannte Dokumentwerte bleiben überprüfbare Vorschläge; Hinweise zu seltenen Angaben öffnen die Details automatisch.

Eine fehlende Bezeichnung wird am Feld und in der Fehlerübersicht angezeigt. Über den Link in der Übersicht gelangst du zurück zum Feld. Schlägt das Speichern wegen eines Server- oder Netzwerkfehlers fehl, bleiben deine Eingaben im Editor erhalten und du kannst erneut speichern. Die Freigabe erklärt vor dem Speichern, wer den Vertrag sehen darf.

## Explizite und abgeleitete Termine

`end_date` ist nur dann eine explizite Dokumentangabe, wenn es als solche gespeichert wurde. Die Kündigungsfrist wird als menschenlesbare Vertragsangabe erhalten, zum Beispiel `30 Tage`, `6 Wochen` oder `3 Monate`; Monatsfristen werden nicht pauschal in 30-Tage-Blöcke umgedeutet.

Aus bestätigten Vertragsdaten berechnet der Contract-Core separat:

- das mögliche Ende der Mindestlaufzeit aus `start_date + minimum_term_months`, falls kein explizites Ende existiert,
- die mögliche Kündigungsfrist aus Vertragsende/Mindestlaufzeitende minus der bestätigten Kündigungsfrist.

Diese Werte werden als `source_type="derived"` ausgegeben und in der UI ausdrücklich als berechnet markiert. Sie werden nicht als Dokumentfundstelle dargestellt. Kalender-Monate und -Jahre werden kalendarisch gerechnet (zum Beispiel 31. März minus 1 Monat = 28./29. Februar), nicht als Tagesnäherung.

## Folgeaktionen

Nach dem ersten Speichern fragt der Editor ausdrücklich, ob eine Folgeaktion gewünscht ist. Ohne `confirmed=true` legt `/api/contracts/<id>/actions/` nichts an.

Unterstützt sind:

- private Vertragserinnerung (`ContractReminder`),
- kanonische FamilyOS-Aufgabe (`Task`),
- kanonischer Kalendereintrag (`FamilyEvent`),
- keine Folgeaktion.

`Task` und `FamilyEvent` sind heute familienweit sichtbar. Deshalb werden diese beiden Projektionen für private oder selektiv geteilte Verträge serverseitig mit `409 private_contract_action` blockiert. So kann ein privater Vertragsname nicht über ein anderes Domain-Modell in die Familie leaken.

## Sichtbarkeit und Berechtigungen

`Contract.visibility` unterstützt `private`, `family` und `selected`.

- Der Owner darf den Vertrag sehen und verwalten.
- `private` bleibt auf den Owner beschränkt.
- `family` ist für aktive Familienmitglieder lesbar; Bearbeiten wird dadurch nicht automatisch erlaubt.
- `selected` nutzt `ContractAccess` mit `can_view` / `can_manage`.
- Querysets und Objektzugriffe prüfen die aktive Familienmitgliedschaft und liefern bei fremden Familien bzw. nicht sichtbaren Objekten fail-closed `404`.

Dokumente können nur verknüpft werden, wenn sie zur selben Familie gehören und für den handelnden Nutzer sichtbar sind. Vertragspayloads geben nur verknüpfte Dokumente aus, die der Nutzer ebenfalls sehen darf.

## API

- `GET|POST /api/contracts/`
- `GET|PATCH|DELETE /api/contracts/<id>/`
- `GET /api/contracts/prefill/?family=<family>&document=<document>`
- `POST /api/contracts/<id>/documents/`
- `DELETE /api/contracts/<id>/documents/<document>/`
- `POST /api/contracts/<id>/actions/`

`DELETE` archiviert den Vertrag. Dokumente bleiben eigenständige kanonische Dateien und werden nicht gelöscht.

## Migration und Rollback

`contracts.0001_initial` legt ausschließlich neue Contract-Tabellen und Indizes an. Es gibt keinen Daten-Backfill.

`DocumentLink` ist absichtlich generisch und besitzt keinen Foreign Key auf `Contract`. Deshalb führt die Reverse-Migration zuerst einen Cleanup aller `DocumentLink`-Zeilen mit `domain_type="contract"` aus und droppt danach die Contract-Tabellen. Die Dokumente selbst bleiben dabei erhalten.

Vor einem produktiven Rollback sollte geprüft werden, ob Contract-Daten exportiert werden müssen. Ein Rollback löscht die fachlichen Vertragsdatensätze, aber weder kanonische Dokumentdateien noch andere Domain-Objekte.

## Tests

Die Contract-Tests decken insbesondere ab:

- vollständig manuellen Vertrag ohne Datei,
- private Isolation und familienweite Lesbarkeit,
- Cross-family-Fail-Closed-Verhalten,
- gleiche-Familie/ACL-Anforderungen für Dokumentlinks,
- Mapping der echten Document-Core-Vertrags-Keys inklusive deutschem Datumsformat,
- ergänzendes lokales Prefill inklusive Confidence, Beleg, Seite und `explicit`/`derived`,
- bestätigungspflichtige Folgeaktionen,
- Privacy-Block für Task/Event bei privaten Verträgen,
- kalendarische Monatsfristen sowie abgeleitete Mindestlaufzeit- und Kündigungstermine.
