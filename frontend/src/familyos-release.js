export const FAMILYOS_RELEASE_SCHEMA_VERSION=1;
export const FAMILYOS_RELEASE_URL='/familyos-release.json';
const VERSION_PATTERN=/^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$/;
const DATE_PATTERN=/^\d{4}-\d{2}-\d{2}$/;
const REQUIRED_LOCALES=['de','en'];

function validFeature(feature){
 return Boolean(feature&&typeof feature==='object'&&typeof feature.id==='string'&&feature.id.trim()&&typeof feature.title==='string'&&feature.title.trim()&&typeof feature.description==='string'&&feature.description.trim());
}

export function parseFamilyOsReleaseManifest(value){
 if(!value||typeof value!=='object'||Array.isArray(value))throw new Error('release manifest must be an object');
 if(value.schema_version!==FAMILYOS_RELEASE_SCHEMA_VERSION)throw new Error(`unsupported release manifest schema ${value.schema_version}`);
 if(typeof value.version!=='string'||!VERSION_PATTERN.test(value.version))throw new Error('release manifest version must be semver');
 if(typeof value.released_at!=='string'||!DATE_PATTERN.test(value.released_at)||Number.isNaN(Date.parse(`${value.released_at}T00:00:00Z`)))throw new Error('release manifest released_at must be an ISO date');
 if(!value.features||typeof value.features!=='object'||Array.isArray(value.features))throw new Error('release manifest features must be localized');
 for(const locale of REQUIRED_LOCALES){
  if(!Array.isArray(value.features[locale])||value.features[locale].length===0||!value.features[locale].every(validFeature))throw new Error(`release manifest requires valid ${locale} features`);
 }
 for(const [locale,features] of Object.entries(value.features)){
  if(!/^[a-z]{2}(?:-[A-Z]{2})?$/.test(locale)||!Array.isArray(features)||!features.every(validFeature))throw new Error(`invalid release manifest locale ${locale}`);
  const ids=new Set(features.map(feature=>feature.id));
  if(ids.size!==features.length)throw new Error(`duplicate release feature id in ${locale}`);
 }
 return value;
}

export function releaseFeaturesForLanguage(manifest,language){
 const locale=String(language||'de').split('-')[0];
 return manifest.features[locale]||manifest.features.en||manifest.features.de;
}

export async function loadFamilyOsReleaseManifest(fetchImpl=fetch){
 const response=await fetchImpl(FAMILYOS_RELEASE_URL,{cache:'no-store',headers:{Accept:'application/json'}});
 if(!response.ok)throw new Error(`release manifest request failed (${response.status})`);
 return parseFamilyOsReleaseManifest(await response.json());
}
