import fs from 'node:fs';
import path from 'node:path';
import process from 'node:process';

const root=process.cwd();
const files=['src/SmartLists.jsx','src/SmartEditors.jsx','src/ListEditor.jsx','src/AutomationHub.jsx','src/CalendarHub.jsx','src/IntegrationHub.jsx','src/TodayHome.jsx'];
const localeFiles=new Set(['src/CalendarHub.jsx','src/IntegrationHub.jsx','src/TodayHome.jsx']);
const forbidden=[
  'Aufgabe löschen?','Artikel löschen?','Liste bearbeiten','Familien-Gedächtnis','Schon mal eingetragen',
  'Häufig verwendet','Einkauf abschließen?','Gemeinsam einkaufen','Im Laden','Regel löschen?',
  'Regel jetzt testen?','Eigene Regel','Schnellvorlagen','Keine weiteren Angaben nötig','Quelle auswählen',
  'Vergangene anzeigen','Vergangene ausblenden','Ganztägig','Kalenderquellen','Synchronisierung fehlgeschlagen',
  'Erneut versuchen','Nur ansehen','Keine Quelle gefunden','Verbindung braucht Aufmerksamkeit'
];
let failed=false;
for(const rel of files){
  const text=fs.readFileSync(path.join(root,rel),'utf8');
  for(const phrase of forbidden){
    if(text.includes(`'${phrase}'`)||text.includes(`\"${phrase}\"`)||text.includes(`>${phrase}<`)||text.includes(`${phrase}</`)){
      console.error(`[i18n] ${rel}: hardcoded UI text found: ${phrase}`);
      failed=true;
    }
  }
  if(localeFiles.has(rel)&&/Intl\.(?:DateTimeFormat|RelativeTimeFormat)\(\s*undefined\b/.test(text)){
    console.error(`[i18n] ${rel}: Intl formatter must use the selected app locale`);
    failed=true;
  }
}

function requireText(rel,needles){
 const text=fs.readFileSync(path.join(root,rel),'utf8');
 for(const needle of needles){
  if(!text.includes(needle)){
   console.error(`[i18n] ${rel}: missing required language contract: ${needle}`);
   failed=true;
  }
 }
}

requireText('src/language-options.js',["code:'de'","code:'en'","code:'fr'","code:'nl'","code:'th'",'Français','Nederlands','ไทย']);
requireText('src/locale.js',["fr:'fr-FR'","nl:'nl-NL'","th:'th-TH'"]);
requireText('src/additional-language-i18n.js',["fr:['en']","nl:['en']","th:['en']",'frFeatures','nlFeatures','thFeatures','frCare','nlCare','thCare']);
requireText('src/weather-ui.js',['fr:{','nl:{','th:{']);
requireText('src/waste-ui.js',['fr:{','nl:{','th:{']);

const translationFiles=[
 'src/i18n-extra/fr.js','src/i18n-extra/fr-care.js','src/i18n-extra/fr-features.js',
 'src/i18n-extra/nl.js','src/i18n-extra/nl-care.js','src/i18n-extra/nl-features.js',
 'src/i18n-extra/th.js','src/i18n-extra/th-care.js','src/i18n-extra/th-features.js',
];
for(const rel of translationFiles){
 const text=fs.readFileSync(path.join(root,rel),'utf8');
 if(!text.includes('export const translation={')){
  console.error(`[i18n] ${rel}: translation bundle export missing`);
  failed=true;
 }
 if(!text.includes('{{count}}')||!text.includes('{{name}}')){
  console.error(`[i18n] ${rel}: interpolation placeholders were unexpectedly lost`);
  failed=true;
 }
}

if(failed)process.exit(1);
console.log('[i18n] core UI locale/hardcode guard passed for de/en/fr/nl/th');
