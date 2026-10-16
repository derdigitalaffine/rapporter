import i18n from './create-i18n';

const de={receiptIntelligence:{
 title:'Beleg-Erkennung',subtitle:'Serverseitig erkannte Hinweise – bitte vor dem Speichern prüfen.',
 ocrConfidence:'OCR-Lesbarkeit',semanticConfidence:'Feld-Erkennung',notAvailable:'Kein belastbares Signal',
 reviewNeeded:'Manuelle Prüfung empfohlen',reviewClear:'Keine zusätzlichen Warnsignale erkannt.',
 reasons:{ocr_confidence_low:'Der Text wurde nur mit niedriger OCR-Sicherheit gelesen.',total_missing:'Kein belastbarer Gesamtbetrag erkannt.',total_confidence_low:'Der Gesamtbetrag ist unsicher.',total_ambiguous:'Mehrere Gesamtbeträge sind ähnlich plausibel.',reconciliation_mismatch:'Erkannte Summen und Positionen passen nicht zusammen.'},
 time:'Uhrzeit',receiptId:'Beleg-/Transaktionsnummer',subtotal:'Zwischensumme',tax:'MwSt. / Steuer',
 reconciliationTitle:'Summenabgleich',reconciliation:{matched:'Summen stimmen innerhalb der Toleranz überein.',mismatch:'Summen weichen voneinander ab – bitte Beleg und Betrag prüfen.',partial:'Es gibt einen Teilabgleich, aber nicht genug unabhängige Signale.',insufficient:'Nicht genug unabhängige Summen für einen belastbaren Abgleich.'},
 itemSum:'Summe erkannter Positionen',lineItems:'Erkannte Positionen',lineItemsHint:'Nur Review-Kandidaten. Positionen werden nicht automatisch aufgeteilt oder gebucht.',quantity:'Menge',unitPrice:'Einzelpreis',itemsCount:'{{count}} Positionen',
 evidence:'Evidence anzeigen',evidenceHint:'Rohtext-Ausschnitte bleiben getrennt von normalisierten Werten.',raw:'Gelesen',normalized:'Normalisiert',confidence:'Sicherheit',
 totalCandidates:'Alternative Gesamtbeträge',score:'Score',noEvidence:'Keine zusätzliche Evidence verfügbar.'
}};
const en={receiptIntelligence:{
 title:'Receipt intelligence',subtitle:'Server-detected signals – review them before saving.',
 ocrConfidence:'OCR readability',semanticConfidence:'Field detection',notAvailable:'No reliable signal',
 reviewNeeded:'Manual review recommended',reviewClear:'No additional review signals detected.',
 reasons:{ocr_confidence_low:'The text was read with low OCR confidence.',total_missing:'No reliable total was detected.',total_confidence_low:'The detected total is uncertain.',total_ambiguous:'Several totals are similarly plausible.',reconciliation_mismatch:'Detected totals and line items do not reconcile.'},
 time:'Time',receiptId:'Receipt / transaction number',subtotal:'Subtotal',tax:'Tax / VAT',
 reconciliationTitle:'Reconciliation',reconciliation:{matched:'Detected sums match within tolerance.',mismatch:'Detected sums differ – review the receipt and total.',partial:'A partial check is available, but independent evidence is limited.',insufficient:'There is not enough independent evidence for a reliable reconciliation.'},
 itemSum:'Detected line-item sum',lineItems:'Detected line items',lineItemsHint:'Review candidates only. Items are not split or booked automatically.',quantity:'Quantity',unitPrice:'Unit price',itemsCount:'{{count}} items',
 evidence:'Show evidence',evidenceHint:'Raw text snippets stay separate from normalized values.',raw:'Read',normalized:'Normalized',confidence:'Confidence',
 totalCandidates:'Alternative totals',score:'Score',noEvidence:'No additional evidence available.'
}};

i18n.addResourceBundle('de','translation',de,true,true);
i18n.addResourceBundle('en','translation',en,true,true);
export default i18n;
