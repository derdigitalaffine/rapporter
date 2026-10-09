import fs from 'node:fs';
import path from 'node:path';
import process from 'node:process';

const root=process.cwd();
const files=['src/SmartLists.jsx','src/SmartEditors.jsx','src/ListEditor.jsx','src/AutomationHub.jsx','src/CalendarHub.jsx','src/IntegrationHub.jsx','src/TodayHome.jsx'];
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
  if(/Intl\.(?:DateTimeFormat|RelativeTimeFormat)\(\s*undefined\b/.test(text)){
    console.error(`[i18n] ${rel}: Intl formatter must use the selected app locale`);
    failed=true;
  }
}
if(failed)process.exit(1);
console.log('[i18n] core UI locale/hardcode guard passed');
