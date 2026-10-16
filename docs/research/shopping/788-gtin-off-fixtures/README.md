# #788 – Optionales GTIN-/Open-Food-Facts-Testpaket

Dieses Verzeichnis ist ein **Research-/Fixture-Artefakt** für #788 und den Paketvertrag aus #785. Es ist kein Runtime-Core, kein Pflichtseed und keine Produktverwaltung. Generische Einkaufsartikel bleiben ohne Barcode anlegbar.

## Entscheidung

| Quelle/Pfad | Entscheidung | Zweck | Rechte/Betrieb |
| --- | --- | --- | --- |
| Open Food Facts API v3.6 | **adapt** | gezielte Verifikation einzelner Produkte, Entwicklung und Fehleranalyse | Datenbank ODbL 1.0, einzelne Inhalte DbCL 1.0; Bilder separat CC-BY-SA und hier ausgeschlossen. Custom User-Agent; aktuelle Rate Limits respektieren. |
| Open Food Facts Exporte/Delta-Updates | **adopt für spätere Bulk-Quelle nach Lizenzreview** | reproduzierbare größere Imports | Für mehr als einige hundert Produkte von OFF empfohlen; isolierter Lizenz-/Attributionsbereich, versionierte/pinned Quelle und reversible Aktivierung erforderlich. |
| Open Food Facts API-Suche pro Tastendruck | **defer / verboten** | — | OFF rät von Search-as-you-type ab; Suchrate ist begrenzt. Runtime muss lokal/paketbasiert suchen. |
| Händlerdaten/-APIs | **defer** | mögliche spätere Ergänzung | Nur mit nachgewiesenem API- und Weiterverteilungsrecht. Online-Verfügbarkeit beweist weder Filialbestand noch Preis. Kein Scraping/Auth-/Robots-Umgehen. |
| GTIN-Länderpräfix als Herkunfts- oder Verfügbarkeitsbeweis | **verboten** | — | Ein GS1-Präfix belegt weder Herstellungsland noch Verkauf in Deutschland. |

## Aktuell verifizierte OFF-Betriebsgrenzen

Stand 2026-10-16 dokumentiert die OFF-API-Dokumentation v3.6 als aktuelle Version; v2 ist deprecated. Für Reads nennt sie 15 Produktabfragen/min/IP und 10 Suchabfragen/min/IP. Search-as-you-type wird ausdrücklich abgeraten; für mehr als einige hundert Produkte sollen Exporte statt API-Crawling verwendet werden. Diese Werte sind **kein dauerhaft eingebrannter Runtime-Vertrag**: ein späterer Adapter muss die jeweils aktuelle OFF-Dokumentation/Policy prüfen.

## Paketinhalt

- `products.csv`: zwei kleine, dokumentierte Produktbeispiele mit gültiger GTIN, Minimalfeldern und Provenienz.
- `eval-cases.csv`: positive, negative und Abstention-Fälle für Barcode vs. Freitext.
- `manifest.json`: Version, Quellenrevisionen, Lizenzgrenzen, Counts und Checksums.
- `LICENSE-DATA.md`: getrennte Lizenz-/Attributionshinweise für OFF-bezogene Daten.
- `validate.py`: deterministische GTIN-/Schema-/Eval-Validierung.

Die beiden positiven Produkte stammen aus der dokumentierten CSV-Beispieltabelle in `openfoodfacts/data-imports` (`docs/data-formats.md`, Revision `a2237a59211867646c79cb8673214d4dc12af8da`). Die Tabelle nennt für Nutella ausdrücklich `FR, DE, GB`; das ist **nur Evidenz für den Beispiel-Datensatz**, keine Deutschland-Coverage-Messung und kein Filial-/Preis-/Sortimentsnachweis.

## Normalisierung und Match-Regeln

1. GTIN wird als String gespeichert; führende Nullen dürfen nicht verloren gehen.
2. Erlaubte Längen sind 8, 12, 13 und 14 Ziffern.
3. Die GS1-Modulo-10-Prüfziffer muss stimmen; ungültige Werte werden vor Staging abgewiesen.
4. Exakter gültiger Barcode darf auf genau einen aktiven Fixture-Datensatz zeigen.
5. Freitext wird **nicht** allein wegen schwacher Namensähnlichkeit an eine Marke/ein Produkt gebunden.
6. Mehrdeutige Marken-/Produktnamen führen zu `ABSTAIN`; generische Einträge wie `Milch` bleiben generische Shopping-Items.
7. Gelöschte/fehlerhafte Quellenzeilen werden als Tombstones behandelt; bestehende private Einkaufsdaten werden nie entfernt oder zu OFF hochgeladen.

## Reversibler Importplan für #785

Ein späterer Produktionsimport folgt `staging -> validate -> preview/diff -> atomare Aktivierung`:

- Quelle und Revision pinnen; Download/Export außerhalb des Request-Pfads holen.
- Rohdaten in einen **öffentlichen Referenzdatenbereich** ohne Family-/User-/Shopping-IDs laden.
- Nur benötigte Minimalfelder transformieren: GTIN, Name, Marke, Menge, mappbare Kategorie, Provenienz/Confidence/Status.
- GTIN-Prüfziffer, eindeutige Source-ID, Duplikate, Tombstones und Schema validieren.
- Counts/Checksum/Diff vor Aktivierung anzeigen.
- Aktivierung versioniert und atomar; vorherige gültige Paketversion bleibt rollback-fähig.
- Uninstall/Disable entfernt nur die aktive Referenzversion. Private Listen, manuelle Kategorien und historische Snapshots bleiben erhalten.
- Keine externen Requests pro Keypress; Suchindizes werden lokal aus dem aktiven Paket aufgebaut.

## Lizenzgrenze

OFF-Datenbank, einzelne Datenbankinhalte und Produktbilder haben unterschiedliche Lizenzregime. Dieses Fixture importiert **keine Bilder**. Vor einer produktiven oder kombinierten Datenbankverteilung muss ein Lizenzreview klären, welche ODbL-/DbCL-Pflichten für das konkrete abgeleitete/zusammengeführte Datenbankwerk gelten. Ungeklärte Rechte bedeuten `defer`, nicht stillen Import.

## Coverage und offene Lücken

Dieses Fixture misst **keine Deutschland-Vollständigkeit**. `product_count = 2` ist ausschließlich die Größe des reproduzierbaren Testpakets. Nicht abgedeckt sind insbesondere Händlerverfügbarkeit, Filialsortiment, Preise, Packungswechselhistorie, vollständige DE-Kategorien und belastbare Markt-Coverage. Ein späterer Coverage-Report muss gegen eine definierte Grundgesamtheit und Stichprobe messen.

## Reproduktion

```bash
python3 docs/research/shopping/788-gtin-off-fixtures/validate.py
```

Der Validator führt keine Netzwerkzugriffe aus und verändert keine Runtime-Daten.