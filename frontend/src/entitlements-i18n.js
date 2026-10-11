import i18n from './create-i18n';

const de={entitlementsUi:{
 access:'Familienzugriff',
 tierHint:'Freischaltungen gelten für die ganze Familie.',
 premium:'Premium',
 locked:'gesperrt',
 lockedLabel:'Premium · gesperrt',
 lockedMessage:'{{feature}} ist mit {{tier}} nicht freigeschaltet. Vorhandene Daten bleiben erhalten; Freischaltungen werden familienweit verwaltet.',
}};

const en={entitlementsUi:{
 access:'Family access',
 tierHint:'Access applies to the whole family.',
 premium:'Premium',
 locked:'locked',
 lockedLabel:'Premium · locked',
 lockedMessage:'{{feature}} is not enabled with {{tier}}. Existing data stays intact; access is managed for the whole family.',
}};

i18n.addResourceBundle('de','translation',de,true,true);
i18n.addResourceBundle('en','translation',en,true,true);
export default i18n;
