import i18n from './create-i18n';

const de={budgetCommitments:{
 title:'Budget vormerken',hint:'Reserviere optional Budget für einen geplanten Einkauf. Erst die bestätigte Ausgabe zählt als ausgegeben.',item:'Einkauf',ledger:'Konto',budget:'Budgettopf',overall:'Nur Gesamtbudget',amount:'Vorgemerkt',save:'Vormerken',update:'Vormerkung ändern',release:'Vormerkung aufheben',saved:'Budget vorgemerkt.',released:'Vormerkung aufgehoben.',active:'{{amount}} {{currency}} vorgemerkt',empty:'Keine offenen Einkäufe zum Vormerken.',purchaseHint:'Beim Abhaken öffnet sich die Ausgabe mit dem vorgemerkten Betrag. Du kannst den tatsächlichen Betrag noch ändern.'
}};
const en={budgetCommitments:{
 title:'Reserve budget',hint:'Optionally reserve budget for a planned purchase. Only the confirmed expense counts as spent.',item:'Purchase',ledger:'Account',budget:'Budget',overall:'Overall budget only',amount:'Reserved',save:'Reserve',update:'Update reservation',release:'Release reservation',saved:'Budget reserved.',released:'Reservation released.',active:'{{amount}} {{currency}} reserved',empty:'No open shopping items to reserve.',purchaseHint:'Checking the item opens the expense with the reserved amount. You can still change the actual amount.'
}};

i18n.addResourceBundle('de','translation',de,true,true);
i18n.addResourceBundle('en','translation',en,true,true);
export default i18n;
