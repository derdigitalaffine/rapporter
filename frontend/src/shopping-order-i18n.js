import i18n from './i18n';

const resources={
  de:{label:'Reihenfolge der Einkaufsliste',drag:'{{name}} verschieben',moveUp:'{{name}} nach oben',moveDown:'{{name}} nach unten',moved:'{{name}} verschoben: Position {{position}} von {{count}}',failed:'Reihenfolge konnte nicht gespeichert werden'},
  en:{label:'Shopping list order',drag:'Move {{name}}',moveUp:'Move {{name}} up',moveDown:'Move {{name}} down',moved:'Moved {{name}}: position {{position}} of {{count}}',failed:'Could not save list order'}
};
for(const [language,values] of Object.entries(resources))i18n.addResourceBundle(language,'translation',{shoppingOrder:values},true,true);
