# Shopping: manuelle Reihenfolge und Store Mode

Dieses Dokument beschreibt den UX- und Datenvertrag aus #536.

## Planung: manuelle Artikelreihenfolge

`ShoppingItem.position` ist die kanonische, persistente Reihenfolge innerhalb einer Einkaufsliste. Die Reihenfolge gilt unabhängig davon, ob ein Artikel offen oder erledigt ist.

In der Planung kann ein Artikel am sichtbaren Griff mit Pointer/Touch verschoben werden. Drag & Drop ist nur eine Komfortfunktion: Für jeden Artikel stehen zusätzlich mindestens 44×44 px große Aktionen zum Verschieben nach oben bzw. unten zur Verfügung. Damit bleibt die Funktion per Tastatur und Screenreader vollständig nutzbar.

Ein Reorder wird als vollständige sichtbare Artikelfolge an `POST /api/smart/shopping-lists/<list_id>/reorder/` gesendet. Der Server prüft Family-Zugriff, Duplikate und Vollständigkeit und schreibt anschließend atomar neue Positionen. Check-off, Favorit, Menge, Kategorie oder Gang verändern `position` nicht.

Reorder ist derzeit bewusst online-only. Solange lokale Shopping-Mutationen auf Synchronisierung warten, wird kein paralleler Reorder geschrieben. Dadurch entsteht kein zweiter Konfliktmechanismus neben der bestehenden Offline-Queue.

## Store Mode: Offen, Erledigt, Alle

Der Store Mode startet mit `Offen`. `Erledigt` zeigt bereits abgehakte Artikel und erlaubt das Wiederöffnen. `Alle` zeigt beide Zustände, wobei die manuelle Reihenfolge innerhalb der Statusgruppen stabil bleibt.

Das Abhaken ist optimistisch und bleibt offline-fähig. Erfolgreiche Standardaktionen sind absichtlich leise: Es gibt weder nach jedem Artikel einen Erfolgs-/Undo-Toast noch nach jeder erfolgreichen Synchronisierung einen `Liste synchronisiert`-Toast. Die Zeile bzw. der Statusfilter zeigt die Zustandsänderung direkt.

Fehler, relevante Offline-Zustände und fehlgeschlagene Synchronisierung bleiben sichtbar. Erfolgreiche Synchronisierung ist dagegen der Normalfall und erzeugt keine Benachrichtigungskaskade.

## Barrierefreiheit und Touch

- Reorder hat immer eine Nicht-Drag-Alternative.
- Reorder-Aktionen und Drag-Griff haben mindestens 44×44 px Touchfläche.
- Der Drag-Griff ist die einzige Fläche, die normales Touch-Scrolling für Reorder übernimmt; die restliche Zeile bleibt normal scrollbar.
- Reorder-Ergebnisse werden über eine höfliche Live-Region angekündigt.
- Status wird nicht ausschließlich über Farbe vermittelt.

## Regressionen

Backend-Tests decken Persistenz, Family-Scoping, vollständige Sequenzen und die Unabhängigkeit von Check-off und Reihenfolge ab. Playwright deckt Store-Filter, leises Check-off/Sync sowie tastatur- und pointerbasiertes Planning-Reorder auf Desktop und Mobile ab.
