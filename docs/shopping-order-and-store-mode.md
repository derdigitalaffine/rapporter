# Shopping: manuelle Reihenfolge, Listenwechsel und Store Mode

Dieses Dokument beschreibt den UX- und Datenvertrag aus #536 sowie die darauf aufbauenden Bedienflow-Slices #547 und #549. Für den Store Mode dokumentiert es außerdem den stabilen Sortiermodus aus #780 und den aktuell ausgelieferten Lernvertrag aus #782.

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

Der Store Mode startet im normalen Einkaufsflow mit `Offen`. `Erledigt` zeigt bereits abgehakte Artikel und erlaubt das Wiederöffnen. `Alle` zeigt beide Zustände in derselben aktiven Store-Reihenfolge. Ein Remote-Check verschiebt einen Artikel in `Alle` deshalb nicht allein wegen seines neuen Erledigt-Status an das Ende der Ansicht; persönlicher Filter, Fokus und sichtbarer Laufweg bleiben stabil.

Kategorie-/Gangabschnitte folgen dem realen Laufweg: Entscheidend ist die Position des jeweils ersten sichtbaren Artikels in der kanonischen `ShoppingItem.position`, nicht die alphabetische Bezeichnung der Kategorie oder des Gangs. Eine manuell festgelegte Reihenfolge wird damit nicht durch eine zweite Smart-/Alphabet-Sortierung überschrieben.

Der Store Header ist auf Orientierung reduziert: Zurück, Listenname mit offenem Status und – falls konfiguriert – der Angebotslink. `Artikel hinzufügen` bleibt als persistente Aktion im unteren Store-Footer erreichbar. Ein sichtbarer manueller Refresh ist nicht nötig; die bestehende automatische Aktualisierung bei Online-Wechsel, Rückkehr in den sichtbaren Tab und im Store-Intervall bleibt maßgeblich.

Das Abhaken ist offline-fähig. In `Offen` erhält die Zeile unmittelbar eine kurze Inline-Bestätigung (Häkchen/erledigter Zustand) und verlässt danach ruhig die offene Liste. Bei `prefers-reduced-motion` entfällt die kurze Übergangsverzögerung. Erfolgreiche Standardaktionen sind absichtlich leise: Es gibt weder nach jedem Artikel einen Erfolgs-/Undo-Toast noch nach jeder erfolgreichen Synchronisierung einen `Liste synchronisiert`-Toast. `Erledigt` bleibt der eindeutige Wiederherstellungsweg.

Fehler, relevante Offline-Zustände und fehlgeschlagene Synchronisierung bleiben sichtbar. Erfolgreiche Synchronisierung ist dagegen der Normalfall und erzeugt keine Benachrichtigungskaskade.

## Store-Sortierung: Manuell, Kategorien, Gelernt

Der Store Mode bietet drei bewusst auswählbare Sortierarten: `Manuell`, `Kategorien` und `Gelernt`. Ohne explizite Auswahl ist `Kategorien` der sichere Standard. Die Auswahl ist eine geräte-/browserlokale Präferenz pro Family und konkretem Store; sie wird derzeit in `localStorage` gespeichert und ist keine serverseitige Kontoeinstellung.

Eine Änderung der Auswahl sortiert einen bereits laufenden Einkauf nicht mitten in der Session um. Beim Eintritt in den Store Mode wird ein `orderSnapshot` für diesen Lauf eingefroren. Die geänderte Präferenz gilt beim nächsten Start. Damit bleiben persönliche Scrollposition, Fokus und Wegfolge während eines laufenden Mehrpersonen-Einkaufs unabhängig von späteren Checks oder neuem Lernwissen.

`Manuell` verwendet die kanonische `ShoppingItem.position`. `Kategorien` gruppiert nach Gang/Kategorie auf Basis dieser stabilen Reihenfolge. `Gelernt` wird nur für einen bestätigten konkreten `ShoppingStore` angeboten. Kann keine belastbare gelernte Reihenfolge geliefert werden, fällt der Store Mode sichtbar und nicht blockierend auf Kategorien/kanonische Reihenfolge zurück.

### Datenherkunft und Kausalität von `Gelernt`

Die gelernte Reihenfolge ist **keine zweite persistierte Einkaufs- oder Tracking-Domain**. `GET /api/shopping-stores/<store_id>/learned-order/?shopping_list=<list_id>` berechnet eine abgeleitete Projektion aus den bestehenden kanonischen Shopping-Daten neu.

In die Projektion gehen nur erfolgreich abgeschlossene `ShoppingSession`s für die konkrete Filiale ein. Die unveränderlichen `snapshot.purchased_items` des Checkouts sind die endgültige Wahrheit darüber, welche Artikel tatsächlich gekauft wurden. Historische Check-Events allein machen einen Artikel nicht zu gekaufter Evidenz; ältere abgeschlossene Sessions ohne diesen finalen Snapshot werden für die Lernprojektion nicht erraten.

Die Wegfolge wird pro kausalem Client-Stream ausgewertet. `client_sequence` bestimmt die Reihenfolge innerhalb dieses Streams; Reopen und erneutes Abhaken werden auf den terminalen client-lokalen Zustand normalisiert. Die globale Collaboration-`sequence`, Server-Empfangszeit und Client-Uhr erzeugen keine künstliche Gesamtstrecke zwischen zwei Personen oder Geräten. Parallel `Obst → Brot` und `Milch → TK` wird deshalb nicht zu `Obst → Milch → Brot → TK` vermischt.

Die Projektion ist vorsichtig: einzelne bzw. zu wenige unabhängige Pfade reichen nicht für `source=learned`; widersprüchliche Kanten werden deterministisch behandelt und schwache Evidenz fällt auf die bestehende Reihenfolge zurück. Manuelle Planungspositionen werden durch das Lernen nicht überschrieben.

### Privacy- und Scope-Vertrag

Der breitere familien-/storeweite Lernpool darf nur Beobachtungen aus aktuell familienweit sichtbaren Quelllisten verwenden. Eine explizite `ShoppingListAccess.visibility=family` ist zulässig; Listen ohne Access-Zeile behalten den kanonischen Legacy-Familien-Scope. `private`- und `selected`-Listen werden nicht in diesen breiteren Pool gemischt.

Die Berechtigung wird beim Neuaufbau der Projektion aus dem **aktuellen** Listen-Scope gelesen. Wird eine ehemals familienweite Liste auf `selected` oder `private` verengt, fällt ihre bisherige Evidenz beim nächsten Abruf aus dem breiteren Lernpool. Wird die Quellliste gelöscht, entfernt das bestehende `CASCADE` ihre `ShoppingSession`s und Aktivitäten; daraus kann danach ebenfalls keine gelernte Evidenz mehr entstehen. Dafür gibt es weder einen separaten Tracking-Speicher noch eine Kopie persönlicher Haushaltswege.

### Aus, Retention, Rebuild und Rollback

`Gelernt` ist opt-in. Wer `Manuell` oder `Kategorien` auswählt, verwendet die Lernprojektion beim nächsten Store-Mode-Start nicht. Diese Auswahl ist derzeit der vorhandene **Aus-Schalter für die Nutzung** der Smart-Sortierung.

Das Umschalten auf `Manuell`/`Kategorien` oder das Löschen der lokalen Präferenz ist **kein Daten-Reset**: Es löscht keine Checkout-History und verändert keine kanonischen `ShoppingSession`s. Ein eigener nutzerseitiger „Lerndaten vergessen“-Cutoff ist derzeit noch nicht implementiert und bleibt Teil von #782. Ein solcher Reset darf nicht heimlich die kanonische Kaufhistorie löschen, sondern braucht einen expliziten serverseitigen Evidenz-/Cutoff-Vertrag.

Es gibt aktuell keinen separat persistierten Modell- oder Reihenfolge-Cache, dessen Lebensdauer unabhängig von Shopping-Daten wäre. Die Projektion ist aus den kanonischen Sessions/Activities rebuildbar. Entsprechend folgt ihre aktuell nutzbare Evidenz dem Lebenszyklus und Scope dieser Quelldaten: Scope-Verengung und Listenlöschung wirken beim nächsten Rebuild; eine zusätzliche zeitbasierte Aging-/Retention-Regel für Filialumbauten ist noch nicht ausgeliefert und bleibt in #782 offen.

Rollback ist deshalb ohne Datenmigration möglich: `Gelernt` kann clientseitig nicht gewählt bzw. auf `Kategorien`/`Manuell` zurückgestellt werden, während die kanonischen Checkout-Daten unverändert bleiben. Eine spätere Modellversion, Aging-Regel oder Reset-Grenze muss weiterhin deterministisch aus denselben kanonischen Ereignissen rebuildbar und deaktivierbar bleiben.

## Checkout, Purchase-History und Ausgabe

Der Store Mode schließt einen Einkauf **nie automatisch** ab. Sobald mindestens ein Artikel im Wagen liegt, steht der ruhige CTA `Einkauf abschließen` zur Verfügung. Vor dem Abschluss wird die vorhandene Shopping-Offline-Queue vollständig synchronisiert; ein Checkout baut keinen zweiten Offline-/Konfliktmechanismus auf.

Sind noch offene Artikel vorhanden, fordert das Checkout-Sheet eine bewusste Entscheidung: offene Artikel behalten, offene Artikel entfernen oder abbrechen. Erst danach wird die aktive `ShoppingSession` atomar abgeschlossen. Der Server schreibt davor einen unveränderlichen Snapshot der gekauften und noch offenen, für die abschließende Person sichtbaren Artikel. Gekaufte Artikel werden anschließend aus der wiederverwendbaren aktiven Liste entfernt. Bei `entfernen` gilt dasselbe für die sichtbaren offenen Artikel.

`ShoppingSession` plus Snapshot ist die kanonische Purchase-History. `ShoppingPurchaseEvent` bleibt ausschließlich Prediction-/Learning-Telemetrie und wird nicht zur Checkout-Wahrheit. Historische Snapshots bewahren die Item-Privacy von Geschenk-/Überraschungsartikeln: ein Artikel, der für eine Person verborgen war, wird ihr auch nach dem Löschen des ursprünglichen `ShoppingItem` nicht über die History offengelegt.

Nach dem Abschluss zeigt das Sheet kompakt `N gekauft · M offen` und bietet drei gleichwertige Folgewege:

- **Beleg scannen:** öffnet den bestehenden Expense-Receipt-Flow und damit den kanonischen Document-Processing-/OCR-Pfad.
- **Betrag eingeben:** öffnet den bestehenden Expense-Quick-Flow. Zahler und Beteiligte werden dort sichtbar bestätigt bzw. geändert; Shopping-Sichtbarkeit oder Shopping-Verantwortung werden nicht als Finance-Teilnahme übernommen.
- **Ohne Ausgabe abschließen:** beendet den Shopping-Flow ohne Finance-Objekt.

Eine gespeicherte Expense wird über den kanonischen Context-Link `expense → shopping_session` mit der abgeschlossenen Session verknüpft. Der Link erweitert keine ACL: beide Endpunkte müssen für die lesende Person weiterhin eigenständig sichtbar sein. Finance-/OCR-Fehler machen den bereits abgeschlossenen Einkauf nicht rückgängig.

Beim erfolgreichen Checkout wird die konkrete Session-ID als URL-Zustand (`session=<uuid>`) gesetzt. Ein Reload oder ein Context-Link auf eine abgeschlossene Session öffnet denselben unveränderlichen Snapshot erneut. Beim Schließen dieser historischen Zusammenfassung wird der Session-Parameter entfernt und der normale Store Mode kann mit einer neuen aktiven Session fortfahren.

Serverseitig stehen dafür neben Start/Current/Complete auch ACL-gesicherte Detail- und History-Reads bereit: `GET /api/shopping-sessions/<session_id>/` und `GET /api/shopping-sessions/history/?shopping_list=<list_id>`.

## Barrierefreiheit und Touch

- Reorder hat immer eine Nicht-Drag-Alternative.
- Reorder-Aktionen und Drag-Griff haben mindestens 44×44 px Touchfläche.
- Der Drag-Griff ist die einzige Fläche, die normales Touch-Scrolling für Reorder übernimmt; die restliche Zeile bleibt normal scrollbar.
- Reorder-Ergebnisse werden über eine höfliche Live-Region angekündigt.
- Der Listen-Switcher verwendet eine native Select-Bedienung und mindestens 48 px Höhe; die danebenliegende Listenanlage bietet mindestens 48×48 px Touchfläche.
- Empty-/Completed-State-CTAs sind mindestens 48 px hoch.
- Store Check-off ist per ganzer Checkfläche, Tastatur und Screenreader bedienbar.
- Die kurze Check-off-Transition respektiert `prefers-reduced-motion`.
- Checkout-Aktionen haben mindestens 48 px Höhe und sind ohne Drag-Geste erreichbar.
- Status wird nicht ausschließlich über Farbe vermittelt.

## Regressionen

Backend-Tests decken Persistenz, Family-Scoping, vollständige Sequenzen, die Unabhängigkeit von Check-off und Reihenfolge sowie Checkout-Idempotenz, History-ACLs und Geschenk-Privacy ab. Für die gelernte Store-Reihenfolge decken sie zusätzlich finale Checkout-Käufe, client-lokale Kausalität statt Server-Empfangsreihenfolge, parallele Streams, Reopen/Recheck, Store-Isolation sowie den Ausschluss von `private`/`selected`, Scope-Verengung und Quelllistenlöschung aus dem breiteren Familienpool ab.

Playwright deckt zusätzlich sichtbare/touch-sichere Reorder-Controls, den kompakten Listenwechsel, No-list/Empty/Completed/Offline-Zustände, 320-px-Mobile-Reflow ohne Horizontaloverflow, Desktop-Reflow, reduzierte Planning-Chrome, Laufweg-Gruppierung, Store-Filter, leises Add/Check-off, automatischen Online-Refresh sowie tastatur- und pointerbasiertes Planning-Reorder auf Desktop und Mobile ab. Store-Mode-Regressionen prüfen bei 390×844 außerdem stabile Filter-/Fokus-/Viewport-Reihenfolge bei Live-Checks sowie `prefers-reduced-motion`. Der Checkout-E2E prüft den expliziten Abschluss, Keep/Cancel, die reload-sichere Session-Zusammenfassung, den optionalen Expense-Handoff und den Context-Link zurück zur `ShoppingSession`.
