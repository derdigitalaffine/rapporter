import i18n from './i18n';

const de={offlineReady:'Offline bereit',pending:'Noch nicht synchronisiert',syncing:'Wird synchronisiert …',syncFailed:'Synchronisierung fehlgeschlagen',retry:'Jetzt erneut versuchen',offlineHint:'Änderungen werden auf diesem Gerät gespeichert und bei Verbindung automatisch synchronisiert.',noSnapshot:'Für diese Familie ist noch kein Einkaufsstand offline gespeichert.',queued:'Änderung lokal gespeichert'};
const en={offlineReady:'Offline ready',pending:'Not synced yet',syncing:'Syncing …',syncFailed:'Sync failed',retry:'Try again now',offlineHint:'Changes are stored on this device and sync automatically when the connection returns.',noSnapshot:'No shopping snapshot has been saved offline for this family yet.',queued:'Change saved locally'};

i18n.addResourceBundle('de','translation',{shoppingOffline:de},true,true);
i18n.addResourceBundle('en','translation',{shoppingOffline:en},true,true);
