# Shopping: manuelle Reihenfolge, Listenwechsel und Store Mode

Dieses Dokument beschreibt den UX- und Datenvertrag aus #536 sowie die darauf aufbauenden Bedienflow-Slices #547 und #549.

## Planung: manuelle Artikelreihenfolge

`ShoppingItem.position` ist die kanonische, persistente Reihenfolge innerhalb einer Einkaufsliste. Die Reihenfolge gilt unabhängig davon, ob ein Artikel offen oder erledigt ist.

In der Planung kann ein Artikel am sichtbaren Griff mit Pointer/Touch verschoben werden. Drag & Drop ist nur eine Komfortfunktion: Für jeden Artikel stehen zusätzlich mindestens 44×44 px große Aktionen zum Verschieben nach oben bzw. unten zur Verfügung. Damit bleibt die Funktion per Tastatur und Screenreader vollständig nutzbar. Die Reorder-Bedienelemente bleiben bewusst direkt sichtbar; #547 führt keinen versteckten Sortiermodus ein.

Ein Reorder wird als vollständige sichtbare Artikelfolge an `POST /api/smart/shopping-lists/<list_id>/reorder/` gesendet. Der Server prüft Family-Zugriff, Duplikate und Vollständigkeit und schreibt anschließend atomar neue Positionen. Check-off, Favorit, Menge, Kategorie oder Gang verändern `position` nicht.

Reorder ist derzeit bewusst online-only. Solange lokale Shopping-Mutationen auf Synchronisierung warten, wird kein paralleler Reorder geschrieben. Dadurch entsteht kein zweiter Konfliktmechanismus neben der bestehenden Offline-Queue.

Die Planungsansicht bleibt ruhiger als zuvor: Es gibt keine große Prozent-/Progressdarstellung und keinen permanenten Favoriten-Stern bzw. Favoriten-Badge pro Artikelzeile. Favoriten bleiben im kanonischen Artikel-Editor änderbar. Normales Einzel-Hinzufügen bestätigt sich durch die unmittelbar sichtbare neue Zeile und erzeugt keinen zusätzlichen Success-Toast; Fehlerfeedback bleibt unverändert sichtbar.

## Listenwechsel und Zustände

Mehrere Einkaufslisten werden in der Planung nicht mehr als permanent horizontal scrollende Tab-Leiste dargestellt. Bei mehr als einer Liste gibt es einen kompakten nativen Listen-Switcher. Er zeigt die aktive Liste eindeutig, ist per Touch, Tastatur und Screenreader bedienbar und hält die eigentliche Artikelliste auch bei vielen Listen im Vordergrund. Das Anlegen einer weiteren Liste bleibt direkt daneben erreichbar.

Die Planungsansicht unterscheidet vier Zustände ausdrücklich:

- **Keine Liste:** Es gibt noch kein Shopping-Ziel. Ein primärer CTA öffnet den bestehenden Listen-Anlegeflow; Quick Add wird nicht so dargestellt, als könne bereits in eine konkrete Liste geschrieben werden.
- **Leere Liste:** Die Liste existiert, enthält aber noch keine Artikel. Der primäre CTA fokussiert dieselbe kanonische Quick-Add-Eingabe.
- **Nur erledigte Artikel:** Die Liste ist nicht leer, hat aber keine offenen Artikel mehr. Der Recovery-CTA öffnet den bestehenden Store Mode direkt mit `Erledigt`; es entsteht keine zweite Completed-Ansicht und keine parallele Artikeldomain.
- **Offline/Sync-Fehler:** Offline bleibt als ruhiger persistenter Status sichtbar. Fehlgeschlagene Synchronisierung bleibt davon getrennt als Fehler mit Retry bestehen. Die bestehende Offline-Queue und ihre Konfliktsemantik werden nicht ersetzt. Die Anlage einer neuen Liste ist nicht Teil dieser Queue und wird deshalb offline früh als onlinepflichtig erklärt und gesperrt; Artikelmutationen in bestehenden Listen bleiben weiterhin queue-fähig.

Der Store-Status (`open` oder `done`) kann für diesen Recovery-Pfad als URL-Zustand mitgeführt werden. Ein normaler Einstieg in den Store Mode startet weiterhin mit `Offen`; nur der explizite „Erledigte ansehen“-Pfad startet in `Erledigt`.

## Store Mode: Offen, Erledigt, Alle

Der Store Mode startet im normalen Einkaufsflow mit `Offen`. `Erledigt` zeigt bereits abgehakte Artikel und erlaubt das Wiederöffnen. `Alle` zeigt beide Zustände, wobei die manuelle Reihenfolge innerhalb der Statusgruppen stabil bleibt.

Kategorie-/Gangabschnitte folgen dem realen Laufweg: Entscheidend ist die Position des jeweils ersten sichtbaren Artikels in der kanonischen `ShoppingItem.position`, nicht die alphabetische Bezeichnung der Kategorie oder des Gangs. Eine manuell festgelegte Reihenfolge wird damit nicht durch eine zweite Smart-/Alphabet-Sortierung überschrieben.

Der Store Header ist auf Orientierung reduziert: Zurück, Listenname mit offenem Status und – falls konfiguriert – der Angebotslink. `Artikel hinzufügen` bleibt als persistente Aktion im unteren Store-Footer erreichbar. Ein sichtbarer manueller Refresh ist nicht nötig; die bestehende automatische Aktualisierung bei Online-Wechsel, Rückkehr in den sichtbaren Tab und im Store-Intervall bleibt maßgeblich.

Das Abhaken ist offline-fähig. In `Offen` erhält die Zeile unmittelbar eine kurze Inline-Bestätigung (Häkchen/erledigter Zustand) und verlässt danach ruhig die offene Liste. Bei `prefers-reduced-motion` entfällt die kurze Übergangsverzögerung. Erfolgreiche Standardaktionen sind absichtlich leise: Es gibt weder nach jedem Artikel einen Erfolgs-/Undo-Toast noch nach jeder erfolgreichen Synchronisierung einen `Liste synchronisiert`-Toast. `Erledigt` bleibt der eindeutige Wiederherstellungsweg.

Fehler, relevante Offline-Zustände und fehlgeschlagene Synchronisierung bleiben sichtbar. Erfolgreiche Synchronisierung ist dagegen der Normalfall und erzeugt keine Benachrichtigungskaskade.

## Barrierefreiheit und Touch

- Reorder hat immer eine Nicht-Drag-Alternative.
- Reorder-Aktionen und Drag-Griff haben mindestens 44×44 px Touchfläche.
- Der Drag-Griff ist die einzige Fläche, die normales Touch-Scrolling für Reorder übernimmt; die restliche Zeile bleibt normal scrollbar.
- Reorder-Ergebnisse werden über eine höfliche Live-Region angekündigt.
- Der Listen-Switcher verwendet eine native Select-Bedienung und mindestens 48 px Höhe; die danebenliegende Listenanlage bietet mindestens 48×48 px Touchfläche.
- Empty-/Completed-State-CTAs sind mindestens 48 px hoch.
- Store Check-off ist per ganzer Checkfläche, Tastatur und Screenreader bedienbar.
- Die kurze Check-off-Transition respektiert `prefers-reduced-motion`.
- Status wird nicht ausschließlich über Farbe vermittelt.

## Regressionen

Backend-Tests decken Persistenz, Family-Scoping, vollständige Sequenzen und die Unabhängigkeit von Check-off und Reihenfolge ab. Playwright deckt zusätzlich sichtbare/touch-sichere Reorder-Controls, den kompakten Listenwechsel, No-list/Empty/Completed/Offline-Zustände, 320-px-Mobile-Reflow ohne Horizontaloverflow, Desktop-Reflow, reduzierte Planning-Chrome, Laufweg-Gruppierung, Store-Filter, leises Add/Check-off, automatischen Online-Refresh sowie tastatur- und pointerbasiertes Planning-Reorder auf Desktop und Mobile ab.
