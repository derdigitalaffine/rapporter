# Geld & Finanzen

Unter **Mehr → Geld & Finanzen** findet ihr eure Konten, Buchungen, Budgets und Abrechnungen. Der Bereich ist intern in **Übersicht**, **Ausgaben**, **Budgets**, **Abrechnung** und **Konten** gegliedert. Die Navigation bleibt auf Smartphone und Desktop gleich; auf größeren Bildschirmen wird nur mehr Platz genutzt.

Die **Übersicht** bleibt bewusst kompakt: aktueller Saldo, Budgetstand, letzte Ausgaben und wichtige Hinweise. Detailarbeit findet in der jeweiligen Unterseite statt. Optionale Informationen werden dort aufgeklappt, statt die Übersicht mit Kennzahlen zu füllen.

Das Modul nutzt den normalen FamilyOS-Premium-Zugang. Vor der kommerziellen Umstellung bleibt der bestehende VIP-Zugang erhalten; gespeicherte Buchungen werden bei einem eingeschränkten Zugang nicht gelöscht.

## Konten und Buchungen

Unter **Konten** legt ihr mit **Konto hinzufügen** weitere interne Abrechnungskreise an, etwa Haushalt oder Kreditkarte. Wählt oben das Konto und die Währung. Buchungen, Salden, Budgets und Abrechnungen beziehen sich auf diese Auswahl. Es gibt keine Bankanbindung und keinen automatisch synchronisierten Bankkontostand.

**+ Ausgabe** bleibt im gesamten Finanzbereich schnell erreichbar. Betrag, optionaler Titel und Konto genügen; ein Budget ist keine Pflichtangabe. Über **Details ändern** könnt ihr Datum, Kategorie, Zahlungsart, Budgettopf und Aufteilung anpassen. Persönlich bezahlte Buchungen wirken auf die Salden zwischen Personen. Gemeinsam bezahlte Buchungen zählen zum Budget, erzeugen aber keine Personenschuld. Abrechnungen dokumentieren Zahlungen und führen selbst keine Überweisung aus.

Unter **Ausgaben** zeigt die Liste Datum, Beschreibung, Kategorie, Konto, Betrag und Belegstatus. Auf schmalen Bildschirmen stehen dieselben Informationen in kompakten Zeilen. Suche und Kategorieauswahl filtern die geladenen Buchungen des ausgewählten Kontos und der Währung. Bearbeiten und Löschen sind mit Tastatur und Touch bedienbar.

## Budgets vorausplanen

Unter **Budgets** öffnet **Budget planen** den gemeinsamen Editor. Legt ein **geplantes Gesamtbudget** fest und erfasst bei Bedarf eine separate **Schätzung**. Ein leeres Gesamtbudget bedeutet „noch offen“, `0` dagegen ein bewusst geplantes Nullbudget. Euro- und Centbeträge können mit Komma eingegeben werden.

Unter **Unterbudgets → Kostenbereich hinzufügen** könnt ihr etwa Unterkunft, Transport oder Haushalt planen. Jeder Bereich hat seinen eigenen geplanten Betrag und eine optionale Schätzung. Bearbeiten und Archivieren sind direkt an der Zeile erreichbar. Archivieren entfernt einen Bereich aus der aktiven Planung, behält aber seine bisherigen Ausgaben und Zuordnungen.

**Schätzung**, **Geplant**, **Vorgemerkt** und **Ausgegeben** bleiben verschiedene Fakten. Planung erzeugt keine Buchung, Zahlung oder Personenschuld. Eine Überschreitung warnt sachlich und blockiert keine Ausgabe. Budgets werden immer in der Basiswährung des Kontos angezeigt, auch wenn die Buchungsansicht gerade eine andere Währung filtert.

### Zeitraum & Übertrag

Kostenbereiche können ohne festen Zeitraum, monatlich, jährlich oder für einen festen Datumsbereich geführt werden. Monatliche und jährliche Budgets können am Periodenende entweder **neu starten** oder einen **positiven Rest übertragen**. Ein negativer Rest wird nicht als neue Schuld weitergetragen.

Bereits ausgegebene Beträge werden in der jeweiligen Periode festgehalten. Änderungen am neuen Plan schreiben abgeschlossene Perioden nicht rückwirkend um. Aktive Einkaufsvormerkungen bleiben separate Reservierungen und werden nach einem Periodenwechsel weiter von der verfügbaren Summe abgezogen, ohne doppelt in den Übertrag einzufließen.

Kontextgebundene Zeiträume, zum Beispiel für Reisen, werden vom verknüpften Kontext gesteuert und nicht frei im allgemeinen Finanzeditor erzeugt.

### Teilnehmerplanung

Im aufgeklappten Bereich **Teilnehmerplanung** könnt ihr pro Person zwei voneinander getrennte Werte planen:

- **Persönliches Limit**: eine optionale Planungsgrenze für die Person.
- **Geplanter Kostenanteil**: der erwartete Anteil dieser Person am Budget.

Beide Werte sind nur Planung. Ein persönliches Limit ist keine Zahlung oder Schuld; ein geplanter Kostenanteil ist noch keine tatsächliche Kostenaufteilung und keine Abrechnung. Die Summe der geplanten Anteile darf vom Budget abweichen und blockiert das Speichern nicht.

Owner und Erwachsene dürfen Teilnehmerplanung bearbeiten. Andere berechtigte Familienmitglieder sehen sie nur lesbar: gemeinsame geplante Kostenanteile bleiben sichtbar, persönliche Limits dagegen nur der betroffenen Person und Erwachsenen. Persönliche Limits werden nicht automatisch in Übersicht, Today, Pinnwand, Suche oder Reisekarten übernommen.

Teilnehmerplanung kann sowohl für das Gesamtbudget eines Kontos als auch für einzelne Kostenbereiche verwendet werden. Es wird dafür kein verstecktes zweites Gesamtbudget angelegt.

## Einkaufsvormerkungen

Ein geplanter Einkauf kann einen Betrag in einem Budgettopf **vormerken**. Diese Vormerkung reduziert die verfügbare Summe, ist aber noch keine Ausgabe. Wird der Einkauf tatsächlich gekauft, kann daraus eine normale Ausgabe entstehen und die Vormerkung wird in derselben Aktion verbraucht. Wird die Vormerkung entfernt, entsteht ebenfalls keine Buchung.

Damit bleiben **Vormerkung**, **Ausgabe**, **Kostenaufteilung** und **Abrechnung** getrennte Fakten.

## Reisen und andere Kontexte

Bei einer Reise öffnet **Reisekosten** denselben Finanzbereich mit dem verknüpften Konto und direkt dem passenden Budgetkontext. Dort bearbeitet ihr dieselben Budgets wie über **Mehr → Geld & Finanzen**; es gibt keine separate Reise-Budgetkopie und keinen eigenen `TripBudget`-Bestand.

Persönliche Teilnehmerlimits werden dabei nicht still in Reise-, Today- oder Pinnwandansichten erweitert. Ein Kontext verwendet nur ausdrücklich freigegebene Finanzprojektionen.

## Abrechnung

Unter **Abrechnung** seht ihr offene Personensalden, vorgeschlagene Ausgleiche und bereits dokumentierte Abrechnungen. Geplante Kostenanteile aus der Budgetplanung verändern diese Salden nicht. Nur tatsächliche Ausgabenaufteilungen und erfasste Abrechnungen wirken auf die Schuld-/Guthabenberechnung.

## Speichern, Konflikte und Offline

Bei einem Speicherfehler bleiben eure Eingaben erhalten. Hat jemand die Planung inzwischen geändert, muss zuerst bewusst der aktuelle Stand geladen werden; dabei werden die eigenen Eingaben verworfen. Offline wird keine endgültige Budget-, Teilnehmer-, FX- oder Abrechnungsentscheidung gespeichert.

Die neue Budgetplanung ist additiv zu bestehenden Buchungen, Ausgabenanteilen und Abrechnungen. Werden optionale Teilnehmer-, Perioden- oder Vormerkungsdaten wieder entfernt, bleiben bereits gebuchte Ausgaben, Personensalden und Settlements unverändert.

## Belege und Smartphone-Fotos

Über **Beleg scannen → Beleg auswählen** könnt ihr JPEG, PNG, WebP, HEIC/HEIF oder PDF bis 30 MB hochladen. Der Server prüft den Inhalt unabhängig von Dateiname und Browser-MIME. Bilder werden korrekt ausgerichtet, von Metadaten bereinigt und auf die bewährten Zielgrößen verkleinert. Die Eingangsbilder dürfen höchstens 60 Megapixel und 16384 Pixel je Seite haben.

PDFs werden validiert und unverändert gespeichert, ohne Bildverkleinerung. Passwortgeschützte, ungültige oder mehr als 300 Seiten lange PDFs werden abgelehnt. Nach der Verarbeitung prüft ihr erkannte Angaben und ergänzt fehlende Werte manuell. **Beleg öffnen** zeigt das Bild oder PDF im Browser; dort kann es auch heruntergeladen werden. Belege sind privat, familiengebunden und werden nicht im Offline-Cache gespeichert.

Die größeren Smartphone-Bilder werden auch bei Profil-/Familienbildern, Pinnwand, Messenger und anderen vorhandenen Bild-Uploads serverseitig normalisiert. Die jeweiligen Berechtigungen und Speicherorte bleiben erhalten.
