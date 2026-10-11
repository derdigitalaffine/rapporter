import i18n from './i18n';
import {translation as fr,notes as frNotes} from './i18n-extra/fr';
import {translation as nl,notes as nlNotes} from './i18n-extra/nl';
import {translation as th,notes as thNotes} from './i18n-extra/th';
import {translation as frCare} from './i18n-extra/fr-care';
import {translation as nlCare} from './i18n-extra/nl-care';
import {translation as thCare} from './i18n-extra/th-care';
import {translation as frFeatures} from './i18n-extra/fr-features';
import {translation as nlFeatures} from './i18n-extra/nl-features';
import {translation as thFeatures} from './i18n-extra/th-features';
import {nextAppLanguage,normalizeAppLanguage} from './language-options';

const LANGUAGE_KEY='famuhle-language';
const bundles={
 fr:{translation:{...fr,...frCare,...frFeatures},notes:frNotes},
 nl:{translation:{...nl,...nlCare,...nlFeatures},notes:nlNotes},
 th:{translation:{...th,...thCare,...thFeatures},notes:thNotes},
};
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
function applyLanguage(language,args){
 const resolved=normalizeAppLanguage(language);
 const result=changeLanguageDirect(resolved,...args);
 queueMicrotask(()=>localStorage.setItem(LANGUAGE_KEY,resolved));
 return result;
}
i18n.changeAppLanguage=(language,...args)=>applyLanguage(language,args);
i18n.changeLanguage=(language,...args)=>{
 const current=normalizeAppLanguage(i18n.language);
 const requested=normalizeAppLanguage(language);
 const legacyToggleTarget=current==='de'?'en':'de';
 return applyLanguage(requested===legacyToggleTarget?nextAppLanguage(current):requested,args);
};

export default i18n;
