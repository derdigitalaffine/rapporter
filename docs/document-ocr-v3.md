# Document/OCR v3: serverseitiger OCR- und Receipt-Vertrag

Status: Implementierungsvertrag für #792. Der gemeinsame Document Processing Core aus #180 bleibt die einzige OCR-Infrastruktur; der Receipt-Cutover aus #184 bleibt abgeschlossen.

## Architektur

```text
Upload / Kamera / PDF
→ documents: canonical storage + bounded preprocessing
→ documents: text-first PDF oder lokale Tesseract-TSV-OCR
→ documents: OCR-Evidence, Geometrie, OCR-Confidence, Quality-Metadaten
→ expenses: Receipt-Parser v2
→ semantische Kandidaten + Semantic-Confidence + Reconciliation
→ Review
→ bestätigte Expense-Daten
```

Andere Domains dürfen den Document-Core konsumieren, aber keinen eigenen Tesseract-/OCR-Worker als zweite Wahrheit aufbauen.

## OCR-Arbeitskopie

Die kanonische Datei bleibt unverändert. Für OCR sind nur bounded, lokale Arbeitskopien erlaubt:

- EXIF-Orientierung und kleiner Deskew wie bisher;
- Autocontrast auf der Arbeitskopie;
- kleine Scans dürfen bis zu einem kurzen Rand von 900 px hochskaliert werden, maximal Faktor 2 und maximal 3000 px Arbeitsdimension;
- aggressive 90/180/270-Grad-Rotation und Thresholding sind nicht automatisch aktiv. Die Quality-Metadaten kennzeichnen diese Fallbacks explizit als nicht angewendet, bis ein eigener confidence-gesteuerter Kandidatenpfad implementiert ist;
- born-digital PDFs bleiben text-first und werden nicht unnötig rasterisiert.

`quality_data.pages[*].ocr_workflow` dokumentiert Kandidatenanzahl, gewählte PSM-Strategie, Fallback-Nutzung und den gewählten Evidence-Score. Der Score kombiniert mittlere OCR-Confidence mit Coverage, Zeilenstruktur, Anteil hoch/niedrig sicherer Tokens und alphanumerischer Evidenz; er enthält keinerlei Receipt-/Domainwissen.

## Confidence-Schichten

Drei Signale dürfen nicht vermischt werden:

1. **OCR confidence**: kommt aus `DocumentProcessingRun.quality_data` beziehungsweise den TSV-Tokens und beschreibt, wie zuverlässig Text gelesen wurde.
2. **Semantic confidence**: kommt aus `expenses.ocr.parse_receipt_text` und beschreibt, wie plausibel ein gelesener Wert als Merchant/Datum/Total/etc. ist.
3. **Reconciliation**: vergleicht voneinander unabhängige erkannte Werte. Abweichungen erzeugen Review-Signale; Werte werden niemals verändert, um sie passend zu machen.

## Receipt structured data v2

Der bestehende kompatible Vertrag `merchant`, `date`, `total`, `currency` bleibt erhalten. Additiv liefert der Expense-Adapter:

- `time`;
- `subtotal` nur mit explizitem Label;
- `tax` nur mit explizitem Label;
- `receipt_id` / Transaktionskennung nur mit belastbarem Label;
- konservative `line_items` mit Raw-Evidence und normalisiertem Betrag;
- mehrere `total_candidates` mit Score, Evidence und Scoring-Gründen;
- `reconciliation` mit Delta/Toleranz/Match statt stiller Korrektur;
- `schema_version: 2` und `extractor_version: receipt-v2`;
- `review.reasons`, unter anderem `ocr_confidence_low`, `total_missing`, `total_confidence_low`, `total_ambiguous` und `reconciliation_mismatch`.

Jedes strukturierte Feld hält Raw-Evidence und normalisierten Wert getrennt. Währung wird nur aus expliziten Signalen wie `€`, `EUR`, `USD`, `GBP`, `£` oder `CHF` abgeleitet; ohne Signal bleibt sie unbekannt.

## Total-Ranking und Negativregeln

Starke Labels wie `GESAMT`, `SUMME`, `TOTAL`, `ZAHLBETRAG` oder `ZU ZAHLEN` gewinnen gegen unbeschriftete Beträge. Zeilen mit `gegeben`, `Rückgeld`, Karte/Girocard/Visa/Mastercard, Steuer/MwSt., Subtotal, Telefon/URL oder Beleg-ID werden abgestraft und dürfen nicht allein wegen eines hohen Zahlenwerts zum Total werden.

Sind zwei unterschiedlich hohe Total-Kandidaten fast gleich plausibel, sinkt die Semantic-Confidence und `total_ambiguous` erzwingt Review statt eines scheinbar sicheren Picks.

## Line Items und Reconciliation

Line Items werden nur aus Zeilen mit einer textuellen Beschreibung plus Endbetrag gebildet. Summary-, Tax-, Payment-, Datum-/Zeit-, ID- und Footer-Zeilen werden ausgeschlossen. Ein Muster wie `2 x 1,50 ... 3,00` kann Menge und Einzelpreis zusätzlich liefern.

Reconciliation nutzt ausschließlich erkannte Werte. Beispiele:

- erkannte Positionen ↔ explizite Zwischensumme;
- bei explizitem Netto-Subtotal: Netto + Steuer ↔ Total;
- Positionen ↔ Total ohne belastbares Subtotal bleibt nur ein partielles Signal, weil konservative Line-Item-Extraktion absichtlich Positionen auslassen kann.

Ein Mismatch bleibt sichtbar und verändert weder Total noch Tax noch Subtotal.

## Rollback und Kompatibilität

Keine Migration ist nötig. Die neuen Felder liegen additiv in `ReceiptExtraction.structured_data` und `field_confidences`; der alte Merchant/Date/Total/Currency-Vertrag bleibt erhalten. Bei Parser-Regression kann die strukturierte v2-Auswertung zurückgerollt werden, ohne den Document-Worker, kanonische Dateien oder Raw-OCR anzutasten.

## Nicht-Ziele

- kein Cloud-OCR/LLM im Standardpfad;
- kein zweiter Receipt-/Knowledge-/School-/Pet-OCR-Worker;
- kein Überschreiben von Raw-Evidence durch Normalisierung;
- keine behauptete 100%-Erkennung;
- keine automatische Veröffentlichung unsicherer Buchungsdaten ohne Review.
