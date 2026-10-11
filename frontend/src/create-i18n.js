import i18n from './ux-i18n';

const de={createUi:{
 button:'Hinzufügen',paletteTitle:'Neu hinzufügen',paletteHint:'Was möchtest du für {{family}} anlegen?',quick:'Schnell',more:'Mehr Möglichkeiten',task:'Aufgabe',shoppingItem:'Einkaufsartikel',event:'Termin',expense:'Ausgabe',contract:'Vertrag',correspondence:'Wichtiges Schreiben',wish:'Wunsch',baby:'Schwangerschaft & Baby',pets:'Haustier',taskList:'Aufgabenliste',shoppingList:'Einkaufsliste',routine:'Routine',message:'Mitteilung',loyalty:'Bonuskarte',addNamed:'{{name}} hinzufügen',close:'Erstellen schließen',noActions:'Für deine Rolle sind hier keine Erstellaktionen verfügbar.',chooseBaby:'Wähle ein Baby eindeutig aus.',babyCare:'Pflege erfassen',openPregnancy:'Schwangerschaft öffnen',openBaby:'Schwangerschaft & Baby öffnen',openModuleHint:'Weitere Einträge und Einstellungen im Modul',back:'Zurück',choosePet:'Haustier auswählen',choosePetHint:'Bei mehreren Haustieren muss vor dem Speichern ein eindeutiger Kontext gewählt werden.',petCare:'Versorgung erfassen',openPet:'Haustier öffnen',petHealth:'Beobachtung / Gesundheit'
}};
const en={createUi:{
 button:'Add',paletteTitle:'Add something',paletteHint:'What would you like to create for {{family}}?',quick:'Quick add',more:'More options',task:'Task',shoppingItem:'Shopping item',event:'Event',expense:'Expense',contract:'Contract',correspondence:'Important letter',wish:'Wish',baby:'Pregnancy & baby',pets:'Pet',taskList:'Task list',shoppingList:'Shopping list',routine:'Routine',message:'Message',loyalty:'Loyalty card',addNamed:'Add {{name}}',close:'Close create menu',noActions:'There are no create actions available for your role here.',chooseBaby:'Choose one baby before continuing.',babyCare:'Log care',openPregnancy:'Open pregnancy',openBaby:'Open pregnancy & baby',openModuleHint:'More entries and settings in the module',back:'Back',choosePet:'Choose a pet',choosePetHint:'When there are multiple pets, choose an explicit context before saving.',petCare:'Log care',openPet:'Open pet',petHealth:'Observation / health'
}};

i18n.addResourceBundle('de','translation',de,true,true);
i18n.addResourceBundle('en','translation',en,true,true);
export default i18n;
