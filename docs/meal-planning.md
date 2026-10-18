# Essensplanung

Die Essensplanung ist ein familienweiter Planungsbereich für Gerichte, freie Mahlzeiteneinträge, Mottotage und Wochenvorlagen. Sie ergänzt den bestehenden Einkauf, ersetzt ihn aber nicht.

## Einstieg und Ansichten

Der Essensplan liegt unter **Mehr → Essensplan**. Die Planansicht bietet eine Tages- und eine Wochenansicht. Auf breiten Bildschirmen wird die Woche kalenderartig dargestellt; auf kleinen Bildschirmen werden die Tage untereinander angeordnet, damit kein horizontaler Seiten-Scroll nötig ist.

Auf **Heute** zeigt das Widget **„Was gibt es heute?“** die geplanten Mahlzeiten des aktuellen Familientags. Der Link im Widget öffnet direkt die Tagesansicht.

## Gerichte und freie Einträge

Ein strukturiertes Gericht besitzt:

- einen Namen,
- Standard-Portionen,
- optional den Favoriten-Status,
- frei definierbare Tags/Mottos,
- Zutaten mit optionaler Menge und Einheit,
- pro Zutat optional **„normalerweise vorhanden“**.

Beim Planen kann die Standard-Portionszahl für einen einzelnen Termin überschrieben werden.

Freie Einträge wie **Reste**, **Restaurant** oder **Brotzeit** brauchen kein Gericht. Sie erscheinen im Plan, erzeugen aber bewusst keinen Einkaufsbedarf.

Die Oberfläche bietet zuerst die verständlichen Slots **Frühstück**, **Mittagessen** und **Abendessen**. Über **Eigener Slot** können weitere frei benannte Mahlzeiten genutzt werden. Technisch ist die Planung daher nicht auf die drei Standard-Slots beschränkt.

## Mottotage und Tags

Tags sind familienweit frei benennbar, zum Beispiel:

- Suppentag
- Eintopftag
- Pasta
- Schnell

Ein Tag kann einem Gericht, einem einzelnen Planeintrag oder einem ganzen Tag zugeordnet werden. Tages-Tags sind in Tages- und Wochenansicht direkt sichtbar.

## Favoriten

Gerichte können als Favorit markiert werden. In der Gerichteansicht gibt es einen eigenen Favoritenfilter; beim Planen werden Favoriten im Gerichtsauswahlelement hervorgehoben.

## Wochenvorlagen

Eine aktuelle Woche kann als Vorlage gespeichert werden. Die Vorlage übernimmt:

- Wochentag und Slot,
- Gericht oder freien Eintrag,
- optionale Portionen und Notizen,
- Tags am Planeintrag,
- Tags/Mottos des ganzen Tages.

Beim Anwenden auf eine andere Woche werden dieselben Wochentags-/Slot-Positionen verwendet. Bestehende Einträge desselben Tages und Slots werden dabei gezielt aktualisiert statt dupliziert.

## Einkauf prüfen

**Einkauf bleibt die kanonische Shopping-Domain.** Die Essensplanung besitzt keine zweite Einkaufsliste und kein eigenes ShoppingItem-Modell.

Der Ablauf lautet:

1. **Einkauf prüfen** für die aktuell gewählte Woche öffnen.
2. Zutaten aus strukturierten Gerichten werden anhand der geplanten Portionen hoch- oder heruntergerechnet.
3. Kompatible Zutaten mit gleichem Namen und gleicher Einheit werden zusammengefasst.
4. Zutaten mit **„normalerweise vorhanden“** starten im Review als **Vorhanden**; alle anderen als **Fehlt**.
5. Die Familie korrigiert die Auswahl und bei Bedarf die Mengenangabe.
6. Erst über den bestätigten Shopping-Diff werden fehlende Zutaten in eine bestehende FamilyOS-Einkaufsliste geschrieben.

Es gibt bewusst keinen Lagerbestand, keine Bestandsbewegungen und keinen automatischen Verbrauch.

## Änderungen nach der Übertragung

Wenn sich der Essensplan nach einer Shopping-Übertragung ändert, wird vor dem Schreiben ein expliziter Diff berechnet. Automatisch erzeugte, unveränderte und noch offene Shopping-Zeilen können aktualisiert oder entfernt werden.

FamilyOS schützt dagegen Zeilen, die inzwischen:

- als erledigt markiert wurden oder
- manuell in Name/Menge verändert wurden.

Solche Zeilen werden im Diff als geschützt angezeigt und nicht still überschrieben oder gelöscht. Wiederholte Übertragungen desselben unveränderten Plans erzeugen keine Duplikate.

## Rechte und Sicherheit

Alle Gerichte, Tags, Planeinträge, Vorlagen und Transfer-Metadaten sind an eine Familie gebunden. API-Zugriffe prüfen die Familienmitgliedschaft serverseitig. Referenzen auf Gerichte, Tags oder Einkaufslisten anderer Familien werden abgewiesen.

Das Today-Widget ist nur eine Projektion derselben autorisierten Meal-Plan-Daten und erweitert keine Rechte.

## Datenmodell und Migration

Die additive Migration `family.0253_meal_planning` legt Meal-Planning-Tabellen an. Bestehende Shopping-Tabellen werden nicht ersetzt oder migriert. Interne Transfer-Metadaten referenzieren lediglich kanonische `ShoppingItem`-Zeilen, um idempotente, explizite Update-Diffs zu ermöglichen.

### Rollback

Ein Code-Rollback kann Meal-Planning-UI und -API entfernen, ohne bestehende Einkaufslisten zu verändern. Die Migration kann nur zurückgerollt werden, wenn die gespeicherten Meal-Plan-Daten nicht mehr benötigt werden. Bereits bestätigte kanonische Shopping-Zeilen dürfen bei einem Rollback nicht automatisch gelöscht werden.

## Bewusste Nicht-Ziele

Der erste Slice enthält keine:

- vollständige Vorrats-/Lagerverwaltung,
- MHD- oder Barcodeverwaltung,
- automatische bidirektionale Shopping-Synchronisierung,
- Meal-Prep-/Reste-Portionsbuchhaltung,
- Nährwert-/Kalorienengine,
- automatische KI-Rezeptvorschläge.

Siehe Delivery-Issue #870 sowie die Architekturgrenze in #223.
