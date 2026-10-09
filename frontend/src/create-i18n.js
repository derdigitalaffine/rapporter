import i18n from './ux-i18n';

const de={createUi:{
 button:'Hinzufügen',paletteTitle:'Neu hinzufügen',paletteHint:'Was möchtest du für {{family}} anlegen?',quick:'Schnell',more:'Mehr Möglichkeiten',task:'Aufgabe',shoppingItem:'Einkaufsartikel',event:'Termin',taskList:'Aufgabenliste',shoppingList:'Einkaufsliste',routine:'Routine',message:'Mitteilung',loyalty:'Bonuskarte',addNamed:'{{name}} hinzufügen',close:'Erstellen schließen',noActions:'Für deine Rolle sind hier keine Erstellaktionen verfügbar.'
}};
const en={createUi:{
 button:'Add',paletteTitle:'Add something',paletteHint:'What would you like to create for {{family}}?',quick:'Quick add',more:'More options',task:'Task',shoppingItem:'Shopping item',event:'Event',taskList:'Task list',shoppingList:'Shopping list',routine:'Routine',message:'Message',loyalty:'Loyalty card',addNamed:'Add {{name}}',close:'Close create menu',noActions:'There are no create actions available for your role here.'
}};

i18n.addResourceBundle('de','translation',de,true,true);
i18n.addResourceBundle('en','translation',en,true,true);
export default i18n;
