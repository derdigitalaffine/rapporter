import i18n from './i18n';

const resources={
  de:{switchLabel:'Einkaufsliste wechseln',newList:'Neue Liste',noLists:'Noch keine Einkaufsliste',noListsHint:'Lege eine Liste an und füge danach direkt die ersten Artikel hinzu.',createList:'Einkaufsliste anlegen',empty:'Diese Liste ist noch leer',emptyHint:'Füge den ersten Artikel hinzu – die Eingabe bleibt danach für weitere Artikel bereit.',addFirst:'Ersten Artikel hinzufügen',allDone:'Alles erledigt',allDoneHint:'Alle Artikel dieser Liste sind abgehakt. Erledigte Artikel bleiben wiederherstellbar.',viewDone:'Erledigte ansehen',offline:'Offline – Änderungen bleiben auf diesem Gerät gespeichert.'},
  en:{switchLabel:'Switch shopping list',newList:'New list',noLists:'No shopping list yet',noListsHint:'Create a list, then add the first items right away.',createList:'Create shopping list',empty:'This list is still empty',emptyHint:'Add the first item – the input stays ready for more.',addFirst:'Add first item',allDone:'All done',allDoneHint:'Every item on this list is checked off. Completed items stay recoverable.',viewDone:'View completed',offline:'Offline – changes stay saved on this device.'}
};
for(const [language,values] of Object.entries(resources))i18n.addResourceBundle(language,'translation',{shoppingStates:values},true,true);
