import i18n from './create-i18n';

const de={
 plan:'Budget planen',editOverall:'Gesamtbudget planen',editCategory:'Kostenbereich bearbeiten',newCategory:'Kostenbereich hinzufügen',name:'Kostenbereich',
 overallPlanned:'Geplantes Gesamtbudget',planned:'Geplant',estimated:'Schätzung (optional)',actual:'Ausgegeben',reserved:'Vorgemerkt',available:'Verfügbar',carryover:'Übertrag',notPlanned:'Noch offen',
 save:'Budget speichern',saved:'Budgetplanung gespeichert.',empty:'Noch kein Budget geplant.',
 invalidMoney:'Bitte einen nicht negativen Betrag mit höchstens zwei Nachkommastellen eingeben.',requiredPlan:'Bitte einen geplanten Betrag eingeben.',requiredName:'Bitte einen Namen eingeben.',checkFields:'Bitte prüfe die markierten Felder',
 offline:'Budgetplanung kann offline noch nicht sicher gespeichert werden.',saveFailed:'Budget konnte nicht gespeichert werden.',loadFailed:'Budgetplanung konnte nicht geladen werden.',
 conflict:'Die Budgetplanung wurde inzwischen geändert. Deine Eingaben bleiben erhalten. Laden des aktuellen Stands verwirft deine Eingaben.',
 reload:'Aktuellen Stand laden',archive:'Archivieren',archiveQuestion:'Kostenbereich archivieren?',
 periodSettings:'Zeitraum & Übertrag',periodType:'Budgetzeitraum',periodOpen:'Ohne festen Zeitraum',periodMonth:'Monatlich',periodYear:'Jährlich',periodDateRange:'Fester Zeitraum',periodContext:'Bis Kontextende',
 rolloverPolicy:'Am Periodenende',rolloverReset:'Neu starten',rolloverCarry:'Positiven Rest übertragen',rolloverHint:'Aktive Vormerkungen bleiben erhalten und werden im neuen Zeitraum weiter separat abgezogen.',
 startsOn:'Startdatum',endsOn:'Enddatum',requiredDates:'Für einen festen Zeitraum sind Start- und Enddatum erforderlich.',invalidDateRange:'Das Enddatum darf nicht vor dem Startdatum liegen.',periodCurrent:'Aktueller Zeitraum',
};
const en={
 plan:'Plan budget',editOverall:'Plan overall budget',editCategory:'Edit cost category',newCategory:'Add cost category',name:'Cost category',
 overallPlanned:'Planned overall budget',planned:'Planned',estimated:'Estimate (optional)',actual:'Spent',reserved:'Reserved',available:'Available',carryover:'Carryover',notPlanned:'Not set yet',
 save:'Save budget',saved:'Budget plan saved.',empty:'No budget planned yet.',
 invalidMoney:'Enter a non-negative amount with at most two decimal places.',requiredPlan:'Enter a planned amount.',requiredName:'Enter a name.',checkFields:'Check the highlighted fields',
 offline:'Budget plans cannot yet be saved safely while offline.',saveFailed:'Could not save budget.',loadFailed:'Could not load the budget plan.',
 conflict:'The budget plan has changed. Your inputs are preserved. Loading the current version discards your inputs.',
 reload:'Load current version',archive:'Archive',archiveQuestion:'Archive cost category?',
 periodSettings:'Period & carryover',periodType:'Budget period',periodOpen:'No fixed period',periodMonth:'Monthly',periodYear:'Yearly',periodDateRange:'Fixed date range',periodContext:'Until context ends',
 rolloverPolicy:'At period end',rolloverReset:'Reset',rolloverCarry:'Carry positive remainder',rolloverHint:'Active reservations remain live and continue to reduce availability separately in the new period.',
 startsOn:'Start date',endsOn:'End date',requiredDates:'A fixed date range needs a start and end date.',invalidDateRange:'The end date cannot be before the start date.',periodCurrent:'Current period',
};
for(const [language,resource] of Object.entries({de,en}))i18n.addResourceBundle(language,'translation',{budgetPlanning:resource},true,true);
