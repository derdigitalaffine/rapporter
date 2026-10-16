# Datenlizenz und Attribution für #788

Dieses Verzeichnis enthält ein kleines Research-/Testfixture. Es ersetzt **keine** juristische Prüfung für eine produktive Datenbankverteilung.

## Open Food Facts

Die am 2026-10-16 geprüfte Open-Food-Facts-API-Dokumentation trennt die Rechte wie folgt:

- Datenbank: **Open Database License (ODbL) 1.0**
- einzelne Datenbankinhalte: **Database Contents License (DbCL) 1.0**
- Produktbilder: **CC BY-SA 3.0**, zusätzlich können weitere Rechte an abgebildeten Elementen bestehen

Produktbilder werden in diesem Fixture **nicht** übernommen. Ebenso werden keine unnötigen Ernährungs-, Allergen- oder Zutatenfelder importiert.

Attribution für die OFF-bezogenen Fixtures:

> Contains data/evidence derived from Open Food Facts. Database reuse is subject to ODbL 1.0 and database contents to DbCL 1.0; see the pinned source and current Open Food Facts terms before production redistribution.

## Trennung vom FamilyOS-Quellcode

Die OFF-bezogenen Datensätze werden als eigener Daten-/Referenzbereich behandelt. Die Softwarelizenz des FamilyOS-Repositories darf **nicht** stillschweigend als Datenlizenz dieser Inhalte interpretiert werden. Ein späterer Produktionsimport muss Lizenz- und Attributionsmetadaten bis zum aktivierten Paket erhalten.

## Produktionsfreigabe

Vor Verteilung einer abgeleiteten oder mit anderen Quellen zusammengeführten Produktdatenbank ist zu prüfen, welche ODbL-/DbCL-Pflichten für die konkrete Datenbank gelten. Solange das ungeklärt ist, gilt für den Produktionsimport `defer`.

Offizielle Händlerquellen sind nicht Bestandteil dieses Fixtures. Sie dürfen nur ergänzt werden, wenn API-Nutzung und Weiterverteilung ausdrücklich belegt sind; Login-, Anti-Bot- oder robots.txt-Umgehung ist ausgeschlossen.
