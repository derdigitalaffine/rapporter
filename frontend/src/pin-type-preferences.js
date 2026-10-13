// Convenience uses only adapter type keys, never objects, previews or sharing.
const TYPES=new Set(['task','routine','calendar_event','shopping_item','shopping_list','document','note','trip']);
const PREFIX='familyos-pin-types:v1:';
const memory=new Map();
export const PIN_TYPES_UPDATED_EVENT='familyos:pin-types-updated';

export function pinTypeScope(family,session){
 const userId=session?.authenticated===true?session.user?.id:null;
 const membership=userId!=null?family?.memberships?.find(row=>String(row.user)===String(userId)):null;
 return family?.id&&membership?.id&&membership.role&&membership.role!=='guest'
  ?{userId:String(userId),membershipId:String(membership.id),familyId:String(family.id)}:null;
}
export function pinTypeScopeKey(scope){
 return scope&&[scope.userId,scope.membershipId,scope.familyId].every(value=>typeof value==='string'&&value.length>0)
  ?JSON.stringify([scope.userId,scope.membershipId,scope.familyId]):'';
}
export function pinTypeStorageKey(scope){const key=pinTypeScopeKey(scope);return key?PREFIX+key:''}
function normalize(value){
 if(value!==undefined&&(!value||typeof value!=='object'||Array.isArray(value)||typeof value.enabled!=='boolean'))return {enabled:false,types:[]};
 const enabled=value?.enabled!==false;
 const types=enabled&&Array.isArray(value?.types)?[...new Set(value.types.filter(key=>TYPES.has(key)))].slice(0,3):[];
 return {enabled,types};
}
export function readPinTypePreferences(scope){
 const key=pinTypeStorageKey(scope);if(!key)return {enabled:false,types:[]};
 const fallback=memory.get(key);if(fallback?.volatile)return normalize(fallback.preferences);
 let value;try{value=localStorage.getItem(key)}catch{return normalize(fallback?.preferences)}
 if(value===null)return normalize();
 try{return normalize(JSON.parse(value))}catch{return {enabled:false,types:[]}}
}
export function writePinTypePreferences(scope,value){
 const key=pinTypeStorageKey(scope);if(!key)return {enabled:false,types:[]};
 const preferences=normalize(value);const fallback={preferences,volatile:false};memory.set(key,fallback);
 try{localStorage.setItem(key,JSON.stringify(preferences))}catch{fallback.volatile=true}
 window.dispatchEvent(new CustomEvent(PIN_TYPES_UPDATED_EVENT,{detail:{scopeKey:pinTypeScopeKey(scope),preferences}}));
 return preferences;
}
export function recordPinnedType(scope,type){
 if(!TYPES.has(type)||!pinTypeScopeKey(scope))return;
 const preferences=readPinTypePreferences(scope);
 if(preferences.enabled)writePinTypePreferences(scope,{enabled:true,types:[type,...preferences.types.filter(key=>key!==type)]});
}
