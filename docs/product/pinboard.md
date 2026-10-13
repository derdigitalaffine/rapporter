# Pinnwand

## Composer (#533)

Der Pinnwand-Composer hat genau drei gleichrangige Einstiege: **Notizzettel**, **Foto** und **Vorhandenes Objekt**. Notizzettel bleibt der kurze Text-und-Speichern-Flow. Foto verwendet unverändert die bestehende private Bildpipeline mit maximal vier Bildern; Upload-, Größen- und Metadatenregeln werden nicht im Composer dupliziert.

**Vorhandenes Objekt** verwendet ausschließlich den kanonischen `/api/board/picker/`-Vertrag. Die UI gruppiert Quellen progressiv in To-dos, Kalender, Einkauf, Dokumente und Weitere. Darüber bleiben alle acht Adapter erreichbar: Aufgabe, Routine, Termin, Einkaufsartikel, Einkaufsliste, Dokument, Notiz und Reise. Es gibt keine zweite Domain-Suche und keinen Vollabruf von Events, Tasks, Notes oder Shopping-Listen im Composer.

Der Picker sendet `family`, `adapter_key`, `page`, `page_size` und optional `q`. Bei der Auswahl wird die vom Server bestätigte Legacy-`kind`-Identität zusammen mit `adapter_key` und `target_id` an den bestehenden Board-Create-Endpunkt übergeben. ACL, Lifecycle und Familienzuordnung bleiben vollständig beim jeweiligen Pin-Adapter; der Browser rekonstruiert diese Regeln nicht.

Such-, Adapter-, Familien- und Auth-Wechsel invalidieren laufende Picker-Reads und die aktuelle Auswahl. Eine verspätete Antwort aus einem alten Kontext darf weder Vorschau noch `target_id` wiederherstellen. Pagination bleibt auf dem serverseitig begrenzten Picker. Bei transienten Picker-Fehlern bleibt der Composer offen und kann gezielt erneut laden; bestätigte Create-Requests werden durch den bestehenden Busy-Zustand nicht doppelt ausgelöst.

Native Pins behalten die bestehende Pin-Sichtbarkeit (`Nur du`, `Ausgewählte Personen`, `Familie`). Referenz-Pins übernehmen beim Erstellen weiterhin die aktuelle Source-Sichtbarkeit und erweitern niemals Quellrechte. Bestehende Edit-, Sharing-, Bildentfernungs-, Interaction- und Reorder-Verträge werden durch diesen Slice nicht verändert.

`EntityPicker` unterstützt dafür additiv kontrollierte Server-Suche und lokalisierbare Auswahl-/Entfernen-Texte. Bestehende Aufrufer behalten ihre bisherige lokale Suche und Defaults. Composer-Copy ist für Deutsch, Englisch, Französisch, Niederländisch und Thai vorhanden; die Root- und Picker-Aktionen bleiben mit mindestens 44 px Touchziel, Tastatur und schmalen Viewports nutzbar.

## Scope-Grenze

Der Composer verwendet den bestehenden Pin-/Quellen-Vertrag. Today, Notifications, Models, Migrationen und Source-ACLs bleiben bei ihren kanonischen Cores. Kontextuelle Vorschläge und die weiteren Epic-Kriterien bleiben unter #221 offen.

## Karten und Mehr (#534)

Verknüpfte Karten öffnen ihre kanonische Quelle direkt. Die effektive Sichtbarkeit steht als Text an der Karte; Anpinnen erweitert keine Quellrechte. Kommentare und Reaktionen verwenden dieselbe gemeinsame Interaktionsleiste.

Seltene Aktionen stehen unter **Mehr**: mit Pfeilen die gemeinsame Reihenfolge ändern, die Pin-Sichtbarkeit bearbeiten, die Quelle separat freigeben oder den Pin entfernen. Diese Aktionen erscheinen ausschließlich entsprechend den serverseitigen Fähigkeiten. Die Pfeile sind ohne Drag mit Touch und Tastatur bedienbar und mindestens 44 px hoch. Nach einem Sortierschritt bleibt der Fokus auf Mehr derselben Karte; Escape schließt die Optionen und stellt den Fokus dort wieder her.

Nicht mehr verfügbare Quellen zeigen einen neutralen Zustand ohne alte Beschriftungen, Fotos, Autoren, Metadaten, Kommentare oder Freigabelink. Vom Server erlaubte Pin-Verwaltung bleibt erreichbar. Die Reihenfolge reagiert sofort, Änderungen werden während der Bestätigung serialisiert; ein Fehler stellt die bisherige Reihenfolge wieder her. Familien-/Auth-Wechsel invalidieren alte Reads und Mutationsergebnisse, damit keine verspätete Antwort Karten aus dem vorherigen Kontext zurückbringt.

Der Slice nutzt vorhandene details/summary-Aktionen, den bestehenden Board-Reorder-/Delete-Vertrag und PinInteractionBar. Es entstehen keine neuen Menüs, ACLs, Modelle oder Migrationen. Rollback: UI-Commit zurücknehmen; Daten und Quellrechte bleiben unverändert.
