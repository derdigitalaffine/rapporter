# Shopping: belegbare Filial-Layout-Evidenz und Cold-Start

Status: Rechercheartefakt zu #789. Stand der Quellenpruefung: 2026-10-16.

## Entscheidung

**Kein allgemeines deutsches Filial-Layoutpaket aus Haendlerkarten ausliefern.** Die Recherche belegt, dass konkrete Filialplaene und sogar Indoor-Navigation existieren. Fuer die geprueften Haendlerquellen ist aber kein Recht belegt, diese Grafiken oder daraus systematisch extrahierte Layoutdaten als FamilyOS-Datenpaket weiterzuverteilen.

Fuer #785 gilt deshalb ein zweigleisiger Vertrag:

1. **Belegtes Branch-Paket nur aus einer Quelle mit ausdruecklich kompatiblem Datenrecht.** Aktuell ist OpenStreetMap (ODbL) die einzige gepruefte Quelle, fuer die Weiterverwendung und Weiterverteilung grundsaetzlich belegt sind. Aktivierung erfolgt trotzdem nur pro konkreter Filiale, wenn dort tatsaechlich ausreichend Indoor-/Abteilungsdaten vorhanden und aktuell genug sind.
2. **Haendlerkarten bleiben Evidence-only.** Sie duerfen die Existenz und moegliche Semantik eines filialspezifischen Layouts belegen und manuelle/Eval-Faelle informieren, werden aber ohne zusaetzliche Freigabe weder gespiegelt noch in ein redistributables Dataset abgeschrieben.

Wenn fuer eine konkrete Filiale keine lizenzierbare Branch-Evidenz vorliegt, wird **defer** verwendet. Der Cold-Start darf dann nur eine klar markierte, filialunabhaengige Kategorien-Heuristik nutzen. Diese ist keine Filialkarte und keine behauptete Laufroute.

## Quellen-, Lizenz- und Aktualitaetsmatrix

| Quelle | Beleg | Filialspezifisch | Rechte fuer FamilyOS-Paket | Aktualitaet / Coverage | Entscheidung |
| --- | --- | --- | --- | --- | --- |
| GLOBUS Markthalle Saarlouis, offizieller Marktplan | Der oeffentliche PDF-Plan nennt die konkrete Filiale/Adresse, Abteilungen und Regalnummern, z. B. Milchprodukte 53-58, Wurst 62-67, Tiefkuehlkost 68-73 und Fruehstueck 143-149. | **Ja** | GLOBUS kennzeichnet Texte, Fotos und grafische Gestaltungen seiner Website/App als urheberrechtlich geschuetzt; keine offene Datenlizenz fuer den Marktplan belegt. | URL am 2026-10-16 erreichbar. Keine maschinenlesbare Revisions-/Gueltigkeitsangabe im Plan gefunden; Umbau kann ihn veralten lassen. | **Evidence-only; nicht importieren/spiegeln.** |
| GLOBUS Marktseiten / App | Mehrere aktuelle Marktseiten nennen die GLOBUS-App mit **Indoor-Navigation ueber Einkaufsliste**; das belegt eine produktive filialspezifische Navigationsfaehigkeit bei GLOBUS. | Ja, Service wird auf konkreten Marktseiten angeboten | Keine oeffentliche Dataset-/API-Lizenz fuer Positions-/Layoutdaten gefunden; Website/App-Inhalte sind urheberrechtlich geschuetzt. | Am 2026-10-16 live verifiziert; Service ist nicht auf jeder geprueften Marktseite identisch ausgewiesen. | **Feature-Evidenz, keine Datenquelle.** |
| EDEKA/MARKTKAUF konkrete Marktseiten | Z. B. MARKTKAUF Loehne verlinkt einen konkreten Marktplan fuer Albert-Schweitzer-Str. 13; der PDF-Plan zeigt Abteilungen und Eingaenge. Weitere gepruefte EDEKA/MARKTKAUF-Seiten bieten ebenfalls Marktplaene. | **Ja** | EDEKA weist darauf hin, dass Website-Inhalte urheberrechtlich geschuetzt sind und Bildmaterial/Grafiken nicht gespeichert oder vervielfaeltigt werden duerfen; App-Nutzungsrechte sind auf bestimmungsgemaesse Eigennutzung begrenzt. | Loehne-Seite am 2026-10-16 erreichbar; PDF enthaelt Gestaltungsdatum 28.08.2024. Einzelne Plaene koennen nach Umbauten veralten. | **Evidence-only; Grafiken und extrahiertes Serien-Dataset nicht paketieren.** |
| EDEKA App / Einkaufsliste | Offizielle App-Bedingungen nennen die Einkaufsliste als Dienst; EDEKA-Dokumentation beschreibt kategorisierte/Warengruppen-orientierte Einkaufslisten. | Nicht als konkrete Gang-/Filialgeometrie belegt | App-Inhalte nur im fuer den Dienst noetigen Umfang zur Eigennutzung; keine Redistributionslizenz fuer ein Layoutdataset. | Aktuelle Nutzungsbedingungen gueltig ab 26.07.2026, am 2026-10-16 geprueft. | **Nur Muster fuer Kategorie-Cold-Start, nicht Branch-Evidenz.** |
| OpenStreetMap-Daten | OSM kann `shop=supermarket`, `indoor=area`, `level=*`, `barrier=checkout` und fuer separat gemappte Ladenbereiche `department=store_section` + `vending=*` tragen. Branchbezogene Accessibility-Tags koennen ebenfalls vorhanden sein. | Potenziell ja, pro OSM-Objekt | **ODbL 1.0:** Kopieren, Verteilen und Anpassen erlaubt mit Attribution; bei veroeffentlichten abgeleiteten Datenbanken gelten Share-Alike-Pflichten. | Keine Vollstaendigkeit. `department=store_section` ist laut OSM-Wiki eine weniger verbreitete, aber etablierte Sekundaernutzung. Eine deutsche Vollabdeckung wurde **nicht** nachgewiesen. | **Zulaessige Quelle, aber nur pro Branch nach Coverage-/Freshness-Validierung.** |
| OSM nur als Shop-Punkt/Umriss | Ein Supermarkt-POI oder Gebaeudeumriss belegt Standort/Existenz, aber keine Abteilungsfolge. | Ja fuer Filiale, nein fuer internes Layout | ODbL-kompatibel | Sehr haeufiger als detailliertes Indoor-Mapping; aus blosser Geometrie darf keine Gangordnung erfunden werden. | **Layout: defer.** |

### Gepruefte Primarquellen

- GLOBUS Saarlouis Marktplan: https://www.globus.de/media/redaktionell/maerkte/saarlouis/marktplan_sls_eg_neuerungen.pdf
- GLOBUS Beispiel Marktservice mit Indoor-Navigation: https://www.globus.de/kaiserslautern/services-vor-ort.php
- GLOBUS Impressum / Rechtehinweis: https://www.globus.de/impressum.php
- MARKTKAUF Loehne Marktseite: https://www.edeka.de/maerkte/400643/
- MARKTKAUF Loehne Marktplan: https://www.edeka.de/static/media/eh/edeka-resp/minden-hannover/marktkauf-l%C3%B6hne-albert-schweitzer-str.-13/marktplan-mk-lohne-kompr.pdf
- EDEKA Nutzungsbedingungen: https://www.edeka.de/services/nutzungsbedingungen/
- EDEKA Impressum / Rechtehinweis: https://www.edeka.de/impressum/
- OpenStreetMap Copyright/Lizenz: https://www.openstreetmap.org/copyright/en
- OSMF Attribution Guidelines: https://osmfoundation.org/wiki/Attribution_Guidelines
- OSM Indoor-Shopping-Beispiel: https://wiki.openstreetmap.org/wiki/OpenLevelUp/Use_cases/Shopping_mall
- OSM `department`-Tag: https://wiki.openstreetmap.org/wiki/Key:department

Die Liste ist eine **belegte Stichprobe**, keine Vollstaendigkeitsbehauptung fuer alle deutschen Haendler oder Filialen.

## Positiv- und Negativbeispiele

### Positiv: echte Branch-Evidenz existiert

**GLOBUS Saarlouis** ist ein konkretes Positivbeispiel dafuer, dass ein Haendler einen filialspezifischen Plan mit Abteilungen und Regalnummern oeffentlich bereitstellt. Der Plan darf deshalb als Beleg in Tests/Entscheidungen dienen. Er ist aber **kein importierbarer FamilyOS-Datensatz**, solange das Weiterverteilungsrecht nicht separat geklaert ist.

**MARKTKAUF Loehne** ist ein zweites konkretes Positivbeispiel fuer einen filialspezifischen Plan. Auch hier ist die Existenz der Karte belegt, waehrend die Website-Rechte eine pauschale grafische Weiterverteilung gerade nicht freigeben.

### Negativ: vorhandene Information ist nicht automatisch paketierbar

- Ein oeffentlich abrufbarer PDF-Marktplan ist nicht gleichbedeutend mit Open Data.
- Eine Haendler-App mit Indoor-Navigation ist kein Beleg fuer eine oeffentliche API oder ein Weiterverteilungsrecht.
- Ein OSM-`shop=supermarket`-Objekt ist kein Gangplan.
- Ein `department=store_section`-Schema beweist nicht, dass eine konkrete Filiale vollstaendig so gemappt ist.
- Eine Kette mit mehreren veroeffentlichten Marktplaenen rechtfertigt **keine** Kettenheuristik `chain -> layout`.

## Optionaler #785-Paketvertrag

Ein Branch-Layoutpaket ist nur aktivierbar, wenn jedes Branch-Record auf eine konkrete, nachvollziehbare Quelle zurueckfuehrt und deren Lizenz die beabsichtigte Nutzung erlaubt.

Beispielmanifest (konzeptionell, noch kein Runtime-Schema):

```json
{
  "schema_version": 1,
  "dataset_id": "shopping-store-layout-evidence-de",
  "dataset_version": "2026-10-16.1",
  "kind": "shopping_store_layout_evidence",
  "country": "DE",
  "generated_at": "2026-10-16T00:00:00Z",
  "sources": [
    {
      "source_id": "osm",
      "source_url": "https://www.openstreetmap.org/",
      "licence": "ODbL-1.0",
      "attribution": "OpenStreetMap",
      "redistribution": "allowed-with-ODbL-obligations"
    }
  ],
  "coverage": {
    "claims_complete_germany": false,
    "branch_count": 0
  }
}
```

Ein aktivierbarer Branch-Record braucht mindestens:

```text
branch_ref
  namespace                 # z. B. osm
  source_branch_id          # keine Chain-ID als Ersatz
  country
  address_or_public_geo_ref # nur soweit Quelle/Lizenz erlaubt
source_evidence[]
  source_url
  source_revision           # OSM version/changeset oder vergleichbarer stabiler Stand
  verified_at
  licence
  attribution
  redistribution_allowed
  confidence
levels[]
zones[]
  local_zone_id
  level
  label                     # nur aus erlaubter Quelle oder FamilyOS-eigener Taxonomie
  category_refs[]           # optional; keine implizite Produktverfuegbarkeit
adjacency[]
  zone_a
  zone_b
  evidence                  # ungerichtete Nachbarschaft bevorzugt
entrances[]                 # nur wenn konkret belegt
checkouts[]                 # nur wenn konkret belegt
validity
  observed_at
  source_last_modified
  needs_reverification
```

### Harte Aktivierungsregeln

Ein Branch-Record wird **nicht** aktiviert, wenn einer dieser Punkte zutrifft:

- `redistribution_allowed` ist nicht positiv belegt;
- nur Kette/Marke, aber keine konkrete Filiale ist identifiziert;
- die Quelle zeigt nur Shop-Koordinaten/Umriss ohne interne Bereiche;
- Abteilungen wurden aus einem anderen Markt derselben Kette uebertragen;
- Quelle ist offensichtlich nach einem dokumentierten Umbau entstanden/veraltet oder ihre Gueltigkeit ist nicht mehr verifizierbar;
- das Record enthaelt eine zwingende Gesamtroute, obwohl nur Nachbarschaften/Teilbereiche belegt sind;
- private Familienwege oder Einkaufskoerbe waeren fuer die Erzeugung noetig.

Haendlerkarten ohne Redistributionsrecht duerfen als `external_evidence` in der Recherchematrix referenziert werden, **nicht** als Payload des installierbaren Pakets.

## Validity, Update und Rollback

- Jede aktivierte Branch-Evidenz ist **versioniert und pinned**. Kein stilles Live-Scraping im Einkaufsflow.
- Import speichert Source-Revision/OSM-Version, `verified_at` und einen Content-/Record-Checksum-Wert.
- Updates laufen ueber #785 Staging -> Validierung -> Preview/Diff -> atomare Aktivierung.
- Wegfall eines Branches oder einer belastbaren Abteilung erzeugt Tombstone/Diff; historische ShoppingSessions behalten ihren damaligen Referenz-/Snapshot-Kontext.
- Eine neue Quelle darf ein manuelles FamilyOS-Override nie ueberschreiben.
- Bei Source-Fehler, Lizenzunklarheit, starkem Diff oder fehlender Coverage bleibt die letzte valide Version aktiv oder das Branch-Paket wird deaktiviert; Einkauf bleibt nutzbar.
- Retailer-PDFs werden nicht periodisch heruntergeladen, solange kein vertraglich/lizenzrechtlich geeigneter Source-Adapter existiert.

## Cold-Start ohne Branch-Paket

Der sichere Cold-Start ist eine **eigene, klar markierte Kategorien-Heuristik** und darf nicht so aussehen, als kenne FamilyOS den Grundriss einer REWE-, EDEKA-, Lidl-, Aldi- oder sonstigen Filiale.

Vorgeschlagene Repräsentation:

- ungerichtete Kategorie-Nachbarschaften (`Obst/Gemuese` nahe `Frische`, etc.) oder schwache Teilordnungen;
- keine Meter, Gehzeiten, Gangnummern oder exakten Koordinaten;
- keine Ketten-ID als Beweis fuer Reihenfolge;
- Richtung nicht festschreiben: zwei Personen koennen denselben Markt von unterschiedlichen Enden durchlaufen;
- Zyklen/Widersprueche senken Konfidenz statt eine Zwangstour zu erzeugen;
- neue Erkenntnisse sortieren einen laufenden Store Mode nicht um.

Fallback-Prioritaet fuer einen **neuen** Einkauf:

1. explizite manuelle Reihenfolge/Abteilung;
2. ausreichend belastbares, nach #782 gelerntes Modell fuer genau diese Filiale;
3. aktiviertes, lizenzkonformes Branch-Paket fuer genau diese Filiale;
4. generische Kategorien-/Nachbarschafts-Heuristik;
5. bestehende Planungsreihenfolge / manuell.

Ein laufender Einkauf friert seine Startreihenfolge gemaess #782 ein. Spaete Paket-/Lernergebnisse gelten erst fuer einen spaeteren Start.

## Eval-Faelle fuer #782

1. **Gegenlaeufige Eingaenge:** dieselben Zonen, Person A startet links und B rechts. Erwartung: Nachbarschaften bleiben nutzbar; keine falsche globale Richtung.
2. **Nur Shop-Punkt:** konkrete Filiale ist in OSM vorhanden, aber ohne `indoor`/Sections. Erwartung: Branch-Layout `defer`; generische Kategorien bleiben moeglich.
3. **Teilgemappter Markt:** drei Abteilungen sind belegt, Rest unbekannt. Erwartung: nur diese Kanten/Teilordnung nutzen; Unbekanntes nicht interpolieren.
4. **Mehrstockwerk:** Bereiche auf `level=0` und `level=1`, Verbindung nicht belegt. Erwartung: keine erfundene Treppe/Route; Teilgraphen getrennt lassen.
5. **Umbau:** neuer offizieller Plan widerspricht altem Stand. Erwartung: Paket als stale markieren, Preview-Diff; laufende Session unveraendert.
6. **Temporare Aktionsflaeche:** Aktionsbereich wechselt. Erwartung: keine dauerhafte hohe Konfidenz fuer Aktionsware.
7. **Falsche Kettenuebertragung:** Plan Filiale A wird Filiale B derselben Kette zugeordnet. Erwartung: Validator lehnt wegen Branch-ID/Evidenz-Mismatch ab.
8. **Lizenz fehlt:** offizieller Haendlerplan ist lesbar, Weiterverteilung aber nicht erlaubt. Erwartung: `external_evidence`, kein importierbarer Record.
9. **OSM offen, aber widerspruechlich:** zwei aktuelle OSM-Elemente ergeben unvereinbare Section-Beziehungen. Erwartung: Konfidenz sinkt/defer; kein Zwangspfad.
10. **Manuelle Korrektur:** Nutzer setzt bekannte Abteilung/Reihenfolge. Erwartung: manuell gewinnt und wird von Paketupdate nicht ueberschrieben.
11. **Offline:** aktiviertes Paket ist lokal/cachebar verfuegbar, Update nicht erreichbar. Erwartung: Einkauf funktioniert mit letzter valider Version bzw. ohne Paket.
12. **Deaktivierung/Rollback:** Paket wird entfernt oder auf vorige Version zurueckgesetzt. Erwartung: #782 faellt deterministisch auf Lernen/Heuristik/manuell zurueck, historische Sessionreferenz bleibt erklaerbar.

## Nicht-Ziele

- keine Indoor-GPS-/Personenortung;
- keine Sammlung privater Familienlaufwege fuer oeffentliche Referenzdaten;
- keine Meter-/Zeitersparnisversprechen;
- keine verpflichtende Karten-/Haendler-API im Store Mode;
- kein Scraping/Reverse Engineering von Haendler-Apps oder geschuetzten Marktplaenen;
- kein Versuch, aus Produktverfuegbarkeit, Kettenzugehoerigkeit oder Shop-Koordinaten einen Grundriss zu halluzinieren.

## Ergebnis fuer #789

**Decision: adapt + defer by default.**

- Filialspezifische Layout-Evidenz ist real und fuer einzelne deutsche Maerkte oeffentlich sichtbar.
- Die geprueften Haendlerquellen eignen sich ohne zusaetzliche Rechteklaerung nicht als redistributables FamilyOS-Datenpaket.
- OSM ist lizenzseitig geeignet, aber Detailabdeckung muss pro Filiale validiert werden; keine Deutschland-Vollstaendigkeit wird behauptet.
- #782 erhaelt deshalb robuste Eval-Faelle und einen richtungsneutralen Cold-Start-Vertrag statt einer erfundenen Standardtour.
- #785 kann spaeter konkrete Branch-Pakete aufnehmen, sobald eine Quelle **beides** liefert: ausreichende filialspezifische Evidenz und kompatible Nutzungs-/Weiterverteilungsrechte.
