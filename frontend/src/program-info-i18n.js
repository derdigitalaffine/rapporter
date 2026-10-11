import i18n from './i18n';

const resources={
 de:{title:'Programminfos',version:'Version',familyOs:'FamilyOS',whatsNew:'Neu in FamilyOS',released:'Veröffentlicht am {{date}}',loading:'Neuigkeiten werden geladen …',unavailable:'Die aktuellen FamilyOS-Neuigkeiten sind gerade nicht verfügbar.'},
 en:{title:'Program information',version:'Version',familyOs:'FamilyOS',whatsNew:'What’s new in FamilyOS',released:'Released {{date}}',loading:'Loading latest changes …',unavailable:'The latest FamilyOS changes are currently unavailable.'}
};
for(const [language,values] of Object.entries(resources))i18n.addResourceBundle(language,'translation',{programInfoUi:values},true,true);
