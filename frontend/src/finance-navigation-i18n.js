import i18n from './create-i18n';

const de={financeNav:{
 label:'Bereiche in Geld & Finanzen',overview:'Übersicht',expenses:'Ausgaben',budgets:'Budgets',settlements:'Abrechnung',accounts:'Konten',
 overviewHint:'Gesamtstand, Budget und die letzten Ausgaben auf einen Blick.',expensesHint:'Buchungen durchsuchen, prüfen und bearbeiten.',budgetsHint:'Gesamtbudget und optionale Kostenbereiche für das ausgewählte Konto planen.',settlementsHint:'Offene Salden prüfen, Rückzahlungen planen und Abrechnungen dokumentieren.',accountsHint:'Konten auswählen, neu anlegen und optionale Kontoeinstellungen verwalten.',
 balanceDetails:'Personen im Detail',openSettlements:'{{count}} offene Abrechnung(en)',budgetOverview:'Budgetstand',noBudgetPlan:'Noch kein Gesamtbudget geplant.',manageBudget:'Budget öffnen',latestExpenses:'Letzte Ausgaben',viewAllExpenses:'Alle Ausgaben anzeigen',important:'Wichtig',
 morePlanning:'Weitere Planung',morePlanningHint:'Persönliche Limits und geplante Kostenanteile bleiben getrennte Planungsoptionen. Sie erzeugen weder automatisch eine Ausgabe noch eine Schuld oder Abrechnung.',
 accountList:'Kontenliste',accountCount:'{{count}} Konto/Konten',defaultAccount:'Standard',noAccounts:'Noch keine Konten vorhanden.',accountDetails:'Kontoeinstellungen & Gesamtübersicht',optional:'optional'
}};
const en={financeNav:{
 label:'Money & finances sections',overview:'Overview',expenses:'Expenses',budgets:'Budgets',settlements:'Settlement',accounts:'Accounts',
 overviewHint:'Your balance, budget and latest expenses at a glance.',expensesHint:'Search, review and edit transactions.',budgetsHint:'Plan the overall budget and optional cost categories for the selected account.',settlementsHint:'Review open balances, plan repayments and record settlements.',accountsHint:'Choose accounts, add new ones and manage optional account settings.',
 balanceDetails:'People in detail',openSettlements:'{{count}} open settlement(s)',budgetOverview:'Budget status',noBudgetPlan:'No overall budget planned yet.',manageBudget:'Open budget',latestExpenses:'Latest expenses',viewAllExpenses:'View all expenses',important:'Important',
 morePlanning:'More planning',morePlanningHint:'Personal limits and planned cost shares remain separate planning options. They never create an expense, debt or settlement automatically.',
 accountList:'Account list',accountCount:'{{count}} account(s)',defaultAccount:'Default',noAccounts:'No accounts yet.',accountDetails:'Account settings & overall balance',optional:'optional'
}};

i18n.addResourceBundle('de','translation',de,true,true);
i18n.addResourceBundle('en','translation',en,true,true);
export default i18n;
