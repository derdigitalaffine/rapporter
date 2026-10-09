import i18n from './ux-i18n';

const de={pwaUpdate:{
 title:'Update bereit',message:'Eine neue Version von fam-uh-le ist bereit.',dirtyMessage:'Deine ungespeicherten Eingaben bleiben erhalten, bis du das Update startest.',now:'Jetzt aktualisieren',later:'Später'
}};
const en={pwaUpdate:{
 title:'Update ready',message:'A new version of fam-uh-le is ready.',dirtyMessage:'Your unsaved changes stay in place until you start the update.',now:'Update now',later:'Later'
}};

i18n.addResourceBundle('de','translation',de,true,true);
i18n.addResourceBundle('en','translation',en,true,true);
export default i18n;
