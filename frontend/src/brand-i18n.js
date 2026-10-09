import i18n from './i18n';

const replaceBrand=value=>{
 if(typeof value==='string')return value.replaceAll('fam-uh-le','FamilyOS');
 if(Array.isArray(value))return value.map(replaceBrand);
 if(value&&typeof value==='object')return Object.fromEntries(Object.entries(value).map(([key,item])=>[key,replaceBrand(item)]));
 return value;
};

const addResourceBundle=i18n.addResourceBundle.bind(i18n);
i18n.addResourceBundle=(language,namespace,resources,...args)=>addResourceBundle(language,namespace,replaceBrand(resources),...args);

export default i18n;
