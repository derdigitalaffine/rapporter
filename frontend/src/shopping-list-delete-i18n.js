import i18n from './i18n';

const resources={
 de:{action:'Dauerhaft löschen',title:'Einkaufsliste dauerhaft löschen?',message:'„{{name}}“ wird dauerhaft gelöscht. Alle enthaltenen Artikel werden ebenfalls gelöscht. Das kann nicht rückgängig gemacht werden.',success:'„{{name}}“ wurde dauerhaft gelöscht.',failed:'Einkaufsliste konnte nicht gelöscht werden.'},
 en:{action:'Delete permanently',title:'Permanently delete shopping list?',message:'“{{name}}” will be permanently deleted. All items in the list will be deleted as well. This cannot be undone.',success:'“{{name}}” was permanently deleted.',failed:'The shopping list could not be deleted.'}
};
for(const [language,values] of Object.entries(resources))i18n.addResourceBundle(language,'translation',{shoppingListDelete:values},true,true);
