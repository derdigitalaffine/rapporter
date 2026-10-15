import i18n from './create-i18n';

const de={
 plan:'Budget planen',editOverall:'Gesamtbudget planen',editCategory:'Kostenbereich bearbeiten',newCategory:'Kostenbereich hinzufügen',name:'Kostenbereich',
 overallPlanned:'Geplantes Gesamtbudget',planned:'Geplant',estimated:'Schätzung (optional)',actual:'Ausgegeben',notPlanned:'Noch offen',
 save:'Budget speichern',saved:'Budgetplanung gespeichert.',empty:'Noch kein Budget geplant.',
 invalidMoney:'Bitte einen nicht negativen Betrag mit höchstens zwei Nachkommastellen eingeben.',requiredPlan:'Bitte einen geplanten Betrag eingeben.',requiredName:'Bitte einen Namen eingeben.',checkFields:'Bitte prüfe die markierten Felder',
 offline:'Budgetplanung kann offline noch nicht sicher gespeichert werden.',saveFailed:'Budget konnte nicht gespeichert werden.',loadFailed:'Budgetplanung konnte nicht geladen werden.',
 conflict:'Die Budgetplanung wurde inzwischen geändert. Deine Eingaben bleiben erhalten. Laden des aktuellen Stands verwirft deine Eingaben.',
 reload:'Aktuellen Stand laden',archive:'Archivieren',archiveQuestion:'Kostenbereich archivieren?',
};
const en={
 plan:'Plan budget',editOverall:'Plan overall budget',editCategory:'Edit cost category',newCategory:'Add cost category',name:'Cost category',
 overallPlanned:'Planned overall budget',planned:'Planned',estimated:'Estimate (optional)',actual:'Spent',notPlanned:'Not set yet',
 save:'Save budget',saved:'Budget plan saved.',empty:'No budget planned yet.',
 invalidMoney:'Enter a non-negative amount with at most two decimal places.',requiredPlan:'Enter a planned amount.',requiredName:'Enter a name.',checkFields:'Check the highlighted fields',
 offline:'Budget plans cannot yet be saved safely while offline.',saveFailed:'Could not save budget.',loadFailed:'Could not load the budget plan.',
 conflict:'The budget plan has changed. Your inputs are preserved. Loading the current version discards your inputs.',
 reload:'Load current version',archive:'Archive',archiveQuestion:'Archive cost category?',
};
for(const [language,resource] of Object.entries({de,en}))i18n.addResourceBundle(language,'translation',{budgetPlanning:resource},true,true);
