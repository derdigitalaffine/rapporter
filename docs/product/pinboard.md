# Pinnwand

## Composer (#533)

Der Pinnwand-Composer hat genau drei gleichrangige Einstiege: **Notizzettel**, **Foto** und **Vorhandenes Objekt**. Notizzettel bleibt der kurze Text-und-Speichern-Flow. Foto verwendet unverändert die bestehende private Bildpipeline mit maximal vier Bildern; Upload-, Größen- und Metadatenregeln werden nicht im Composer dupliziert.

**Vorhandenes Objekt** verwendet ausschließlich den kanonischen `/api/board/picker/`-Vertrag. Die UI gruppiert Quellen progressiv in To-dos, Kalender, Einkauf, Dokumente und Weitere. Darüber bleiben alle acht Adapter erreichbar: Aufgabe, Routine, Termin, Einkaufsartikel, Einkaufsliste, Dokument, Notiz und Reise. Es gibt keine zweite Domain-Suche und keinen Vollabruf von Events, Tasks, Notes oder Shopping-Listen im Composer.

Der Picker sendet `family`, `adapter_key`, `page`, `page_size` und optional `q`. Bei der Auswahl wird die vom Server bestätigte Legacy-`kind`-Identität zusammen mit `adapter_key` und `target_id` an den bestehenden Board-Create-Endpunkt übergeben. ACL, Lifecycle und Familienzuordnung bleiben vollständig beim jeweiligen Pin-Adapter; der Browser rekonstruiert diese Regeln nicht.

Such-, Adapter-, Familien- und Auth-Wechsel invalidieren laufende Picker-Reads und die aktuelle Auswahl. Eine verspätete Antwort aus einem alten Kontext darf weder Vorschau noch `target_id` wiederherstellen. Pagination bleibt auf dem serverseitig begrenzten Picker. Bei transienten Picker-Fehlern bleibt der Composer offen und kann gezielt erneut laden; bestätigte Create-Requests werden durch den bestehenden Busy-Zustand nicht doppelt ausgelöst.

Native Pins behalten die bestehende Pin-Sichtbarkeit (`Nur du`, `Ausgewählte Personen`, `Familie`). Referenz-Pins übernehmen beim Erstellen weiterhin die aktuelle Source-Sichtbarkeit und erweitern niemals Quellrechte. Bestehende Edit-, Sharing-, Bildentfernungs-, Interaction- und Reorder-Verträge werden durch diesen Slice nicht verändert.

`EntityPicker` unterstützt dafür additiv kontrollierte Server-Suche und lokalisierbare Auswahl-/Entfernen-Texte. Bestehende Aufrufer behalten ihre bisherige lokale Suche und Defaults. Composer-Copy ist für Deutsch, Englisch, Französisch, Niederländisch und Thai vorhanden; die Root- und Picker-Aktionen bleiben mit mindestens 44 px Touchziel, Tastatur und schmalen Viewports nutzbar.

## Scope-Grenze

Dieser Slice ändert weder PinCard/Mehr/Reorder noch Today, Notifications, Interactions, Models, Migrationen oder Source-ACLs. Diese verbleibenden UX-Teile werden weiterhin unter #221 koordiniert.
