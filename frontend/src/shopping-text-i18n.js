import i18n from './ux-i18n';

const de={shoppingText:{
 mode:'Textmodus',title:'Einkauf zeilenweise',hint:'Mehrere Artikel als Entwurf erfassen, prüfen und gemeinsam übernehmen.',bulkLabel:'Artikel zeilenweise erfassen',bulkPlaceholder:'Milch\n500 g Tomaten\n2 x Wasser 1 l\nKaffee',addLines:'Übernehmen',applying:'Wird übernommen …',pasteHint:'Einfügen und Enter verändern nur den Entwurf. Erst „Übernehmen“ legt Artikel an.',previewTitle:'Vorschau',previewCount:'{{count}} Zeilen',noMetadata:'Keine sichere Mengen- oder Kategorieerkennung',tooManyLines:'Bitte höchstens {{count}} Zeilen pro Übernahme verwenden.',lineFailed:'Zeile konnte nicht übernommen werden.',editLabel:'{{name}} bearbeiten',removeLabel:'{{name}} entfernen',empty:'Noch keine offenen Artikel. Erfasse oben einen Entwurf und übernimm ihn anschließend.',added_one:'{{count}} Artikel hinzugefügt',added_other:'{{count}} Artikel hinzugefügt',updated:'Artikel aktualisiert',removed:'Artikel entfernt'
}};
const en={shoppingText:{
 mode:'Text mode',title:'Shopping line by line',hint:'Capture several items as a draft, review them, then apply them together.',bulkLabel:'Capture items line by line',bulkPlaceholder:'Milk\n500 g tomatoes\n2 x water 1 l\nCoffee',addLines:'Apply',applying:'Applying …',pasteHint:'Paste and Enter only change the draft. Items are created only after “Apply”.',previewTitle:'Preview',previewCount:'{{count}} lines',noMetadata:'No confident quantity or category suggestion',tooManyLines:'Use at most {{count}} lines per apply.',lineFailed:'This line could not be applied.',editLabel:'Edit {{name}}',removeLabel:'Remove {{name}}',empty:'No open items yet. Capture a draft above and apply it when ready.',added_one:'Added {{count}} item',added_other:'Added {{count}} items',updated:'Item updated',removed:'Item removed'
}};

i18n.addResourceBundle('de','translation',de,true,true);
i18n.addResourceBundle('en','translation',en,true,true);
export default i18n;
