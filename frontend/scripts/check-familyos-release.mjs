import {readFile} from 'node:fs/promises';
import {FEATURE_REGISTRY} from '../src/feature-registry.js';
import {parseFamilyOsReleaseManifest} from '../src/familyos-release.js';

const root=new URL('../',import.meta.url);
const [manifestRaw,packageRaw]=await Promise.all([
 readFile(new URL('public/familyos-release.json',root),'utf8'),
 readFile(new URL('package.json',root),'utf8')
]);
const manifest=parseFamilyOsReleaseManifest(JSON.parse(manifestRaw));
const packageMeta=JSON.parse(packageRaw);
if(manifest.version!==packageMeta.version)throw new Error(`familyos-release.json version ${manifest.version} does not match package.json version ${packageMeta.version}`);
const baseline=manifest.features.de.map(feature=>feature.id).join('\n');
for(const [locale,features] of Object.entries(manifest.features)){
 const ids=features.map(feature=>feature.id).join('\n');
 if(ids!==baseline)throw new Error(`familyos-release.json locale ${locale} does not contain the same ordered feature ids as de`);
}

const featureIds=FEATURE_REGISTRY.map(feature=>feature.id);
if(new Set(featureIds).size!==featureIds.length)throw new Error('feature-registry contains duplicate feature ids');
for(const required of ['home','more'])if(!featureIds.includes(required))throw new Error(`feature-registry is missing required page ${required}`);
for(const feature of FEATURE_REGISTRY){
 if(!/^[a-z][a-z0-9_-]*$/.test(feature.id))throw new Error(`feature-registry contains invalid id ${feature.id}`);
 if(feature.queryParams.includes('page'))throw new Error(`feature-registry ${feature.id} must not own reserved query param page`);
 if(new Set(feature.queryParams).size!==feature.queryParams.length)throw new Error(`feature-registry ${feature.id} contains duplicate query params`);
}

console.log(`FamilyOS release manifest ${manifest.version} is valid (${Object.keys(manifest.features).join(', ')})`);
console.log(`FamilyOS feature registry is valid (${featureIds.length} pages)`);
