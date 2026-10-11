import i18n from './ux-i18n';

const de={wishlistUi:{
 title:'Wunschlisten',short:'Wünsche',empty:'Noch keine für dich sichtbaren Wunschlisten.',emptyItems:'Noch keine Wünsche auf dieser Liste.',
 newWish:'Wunsch hinzufügen',newList:'Neue Wunschliste',wish:'Wunsch',list:'Wunschliste',listTitle:'Name der Liste',
 wishTitle:'Wunsch',url:'HTTPS-Link (optional)',note:'Notiz (optional)',priority:'Priorität',priorityNone:'Keine',low:'Niedrig',normal:'Normal',high:'Hoch',
 visibility:'Sichtbarkeit',selected:'Ausgewählte Personen',family:'Ganze Familie',selectedHint:'Nur ausgewählte Personen sehen die Liste. Ohne Auswahl bleibt sie nur für dich sichtbar.',familyHint:'Alle aktiven Familienmitglieder können die Liste sehen.',
 access:'Darf die Liste sehen',save:'Speichern',saving:'Speichert …',saved:'Gespeichert',close:'Schließen',back:'Zurück',
 owner:'Von {{name}}',yourList:'Deine Liste',settings:'Listeneinstellungen',settingsSaved:'Listeneinstellungen gespeichert.',
 reserve:'Reservieren',reserved:'Reserviert',purchased:'Gekauft',markPurchased:'Als gekauft markieren',release:'Freigeben',reservedBy:'Reserviert von {{name}}',purchasedBy:'Gekauft von {{name}}',
 surpriseOwner:'Reservierungen und Kaufstatus werden dir als Listenbesitzer absichtlich nicht angezeigt.',
 coordination:'Geschenkkoordination',actionTitle:'Folgeaktion',actionHint:'Folgeaktionen werden erst nach deiner Bestätigung angelegt.',task:'Aufgabe',shopping:'Einkaufsartikel',expense:'Ausgabe',createAction:'Bestätigt anlegen',
 shoppingList:'Einkaufsliste',amount:'Betrag',currency:'Währung',expenseAck:'Ich verstehe, dass die Ausgabe im aktuellen Ausgabenmodul familienweit sichtbar ist.',
 selectedActionBlocked:'Diese Liste ist nur ausgewählt sichtbar. Familienweite Aufgabe/Einkauf/Ausgabe bleibt deshalb gesperrt.',
 noShoppingList:'Keine Einkaufsliste verfügbar.',openLink:'Link öffnen',archiveItem:'Wunsch entfernen',archived:'Entfernt',
 loadFailed:'Wunschlisten konnten nicht geladen werden.',actionCreated:'Folgeaktion angelegt.',reservationSaved:'Geschenkstatus gespeichert.',reservationReleased:'Reservierung freigegeben.',
 adultCoreHint:'Eigene Wunschlisten sind im Core zunächst für Erwachsene verfügbar; Teen-Eigentümerschaft wird separat freigeschaltet.'
}};
const en={wishlistUi:{
 title:'Wishlists',short:'Wishes',empty:'No wishlists are visible to you yet.',emptyItems:'No wishes on this list yet.',
 newWish:'Add wish',newList:'New wishlist',wish:'Wish',list:'Wishlist',listTitle:'List name',
 wishTitle:'Wish',url:'HTTPS link (optional)',note:'Note (optional)',priority:'Priority',priorityNone:'None',low:'Low',normal:'Normal',high:'High',
 visibility:'Visibility',selected:'Selected people',family:'Whole family',selectedHint:'Only selected people can see this list. With nobody selected it stays owner-only.',familyHint:'All active family members can see the list.',
 access:'Can see the list',save:'Save',saving:'Saving …',saved:'Saved',close:'Close',back:'Back',
 owner:'By {{name}}',yourList:'Your list',settings:'List settings',settingsSaved:'List settings saved.',
 reserve:'Reserve',reserved:'Reserved',purchased:'Purchased',markPurchased:'Mark purchased',release:'Release',reservedBy:'Reserved by {{name}}',purchasedBy:'Purchased by {{name}}',
 surpriseOwner:'Reservation and purchase status are deliberately not shown to you as the list owner.',
 coordination:'Gift coordination',actionTitle:'Follow-up',actionHint:'Follow-ups are created only after your confirmation.',task:'Task',shopping:'Shopping item',expense:'Expense',createAction:'Create confirmed',
 shoppingList:'Shopping list',amount:'Amount',currency:'Currency',expenseAck:'I understand that the Expense module currently shows this expense to the whole family.',
 selectedActionBlocked:'This list is visible only to selected people, so family-wide task/shopping/expense projections stay blocked.',
 noShoppingList:'No shopping list available.',openLink:'Open link',archiveItem:'Remove wish',archived:'Removed',
 loadFailed:'Wishlists could not be loaded.',actionCreated:'Follow-up created.',reservationSaved:'Gift status saved.',reservationReleased:'Reservation released.',
 adultCoreHint:'Owning a wishlist is initially enabled for adults in the core; teen ownership is enabled separately.'
}};

i18n.addResourceBundle('de','translation',de,true,true);
i18n.addResourceBundle('en','translation',en,true,true);
export default i18n;
