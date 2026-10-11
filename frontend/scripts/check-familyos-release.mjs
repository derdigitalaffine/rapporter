import {readFile} from 'node:fs/promises';
import {parseFamilyOsReleaseManifest} from '../src/familyos-release.js';

const root=new URL('../',import.meta.url);
const [manifestRaw,packageRaw]=await Promise.all([
 readFile(new URL('public/familyos-release.json',root),'utf8'),
 readFile(new URL('package.json',root),'utf8')
]);
const manifest=parseFamilyOsReleaseManifest(JSON.parse(manifestRaw));
const packageMeta=JSON.parse(packageRaw);
if(manifest.version!==packageMeta.version)throw new Error(`familyos-release.json version ${manifest.version} does not match package.json ${packageMeta.version}`);
const baseline=manifest.features.de.map(feature=>feature.id).join('\n');
for(const [locale,features] of Object.entries(manifest.features)){
 const ids=features.map(feature=>feature.id).join('\n');
 if(ids!==baseline)throw new Error(`familyos-release.json locale ${locale} does not contain the same ordered feature ids as de`);
}
console.log(`FamilyOS release manifest ${manifest.version} is valid (${Object.keys(manifest.features).join(', ')})`);
