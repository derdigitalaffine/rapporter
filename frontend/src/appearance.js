export const APPEARANCE_STORAGE_KEY='famuhle-appearance';
export const DEFAULT_APPEARANCE=Object.freeze({profile:'green',highContrast:false});
const PROFILES=new Set(['green','blue','green-dark','blue-dark']);

export function normalizeAppearance(value={}){
 return {profile:PROFILES.has(value?.profile)?value.profile:DEFAULT_APPEARANCE.profile,highContrast:Boolean(value?.highContrast)};
}

export function readAppearance(storage=globalThis.localStorage){
 try{return normalizeAppearance(JSON.parse(storage?.getItem(APPEARANCE_STORAGE_KEY)||'{}'))}catch{return {...DEFAULT_APPEARANCE}}
}

export function applyAppearance(value,root=globalThis.document?.documentElement){
 const appearance=normalizeAppearance(value);
 if(root){
  root.dataset.colorProfile=appearance.profile;
  root.dataset.highContrast=appearance.highContrast?'true':'false';
  root.style.colorScheme=appearance.highContrast||appearance.profile.endsWith('-dark')?'dark':'light';
 }
 return appearance;
}

export function saveAppearance(value,storage=globalThis.localStorage,root=globalThis.document?.documentElement){
 const appearance=applyAppearance(value,root);
 try{storage?.setItem(APPEARANCE_STORAGE_KEY,JSON.stringify(appearance))}catch{/* Storage may be unavailable in privacy mode. */}
 if(typeof window!=='undefined')window.dispatchEvent(new CustomEvent('famuhle:appearance-changed',{detail:appearance}));
 return appearance;
}

export function initializeAppearance(){return applyAppearance(readAppearance())}

if(typeof document!=='undefined')initializeAppearance();
