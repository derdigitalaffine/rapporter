import i18n from './ux-i18n';

const de={shoppingText:{
 mode:'Textmodus',title:'Einkauf zeilenweise',hint:'Artikel schnell wie in einer Textdatei erfassen und bearbeiten.',bulkLabel:'Artikel zeilenweise hinzufügen',bulkPlaceholder:'Milch\nBrot\nÄpfel\nKaffee',addLines:'Zeilen hinzufügen',pasteHint:'Enter fügt die aktuelle Zeile hinzu. Mehrzeiliges Einfügen wird sofort in einzelne Artikel aufgeteilt.',editLabel:'{{name}} bearbeiten',removeLabel:'{{name}} entfernen',empty:'Noch keine offenen Artikel. Tippe eine Zeile oder füge mehrere Zeilen auf einmal ein.',added_one:'{{count}} Artikel hinzugefügt',added_other:'{{count}} Artikel hinzugefügt',updated:'Artikel aktualisiert',removed:'Artikel entfernt'
}};
const en={shoppingText:{
 mode:'Text mode',title:'Shopping line by line',hint:'Capture and edit items quickly like a simple text file.',bulkLabel:'Add items line by line',bulkPlaceholder:'Milk\nBread\nApples\nCoffee',addLines:'Add lines',pasteHint:'Enter adds the current line. Pasting multiple lines splits them into individual items immediately.',editLabel:'Edit {{name}}',removeLabel:'Remove {{name}}',empty:'No open items yet. Type one line or paste several lines at once.',added_one:'Added {{count}} item',added_other:'Added {{count}} items',updated:'Item updated',removed:'Item removed'
}};

i18n.addResourceBundle('de','translation',de,true,true);
i18n.addResourceBundle('en','translation',en,true,true);
export default i18n;
