import i18n from './i18n';
import {translation as fr,notes as frNotes} from './i18n-extra/fr';
import {translation as nl,notes as nlNotes} from './i18n-extra/nl';
import {translation as th,notes as thNotes} from './i18n-extra/th';
import {nextAppLanguage,normalizeAppLanguage} from './language-options';

const bundles={fr:{translation:fr,notes:frNotes},nl:{translation:nl,notes:nlNotes},th:{translation:th,notes:thNotes}};
for(const [language,namespaces] of Object.entries(bundles)){
 for(const [namespace,resources] of Object.entries(namespaces))i18n.addResourceBundle(language,namespace,resources,true,true);
}

// New languages fall back to English for any feature copy that has not yet
// received a dedicated translation. German stays the product default.
const fallbackLng={fr:['en'],nl:['en'],th:['en'],default:['de']};
i18n.options.fallbackLng=fallbackLng;
if(i18n.services?.languageUtils?.options)i18n.services.languageUtils.options.fallbackLng=fallbackLng;

// The existing app exposes a compact two-state DE/EN toggle in a few legacy
// surfaces. Keep that call contract working while extending it into the full
// supported-language cycle. Explicit selectors can use changeAppLanguage().
const changeLanguageDirect=i18n.changeLanguage.bind(i18n);
i18n.changeAppLanguage=(language,...args)=>changeLanguageDirect(normalizeAppLanguage(language),...args);
i18n.changeLanguage=(language,...args)=>{
 const current=normalizeAppLanguage(i18n.language);
 const requested=normalizeAppLanguage(language);
 const legacyToggleTarget=current==='de'?'en':'de';
 return changeLanguageDirect(requested===legacyToggleTarget?nextAppLanguage(current):requested,...args);
};

export default i18n;
