import i18n from './i18n';

const de={
  pending:'Noch nicht synchronisiert',syncing:'Wird synchronisiert …',pendingCount:'{{count}} Änderung wartet auf Synchronisierung',pendingCount_other:'{{count}} Änderungen warten auf Synchronisierung',failed:'Synchronisierung fehlgeschlagen',failedHint:'Einige Änderungen konnten mehrfach nicht übertragen werden.',retry:'Jetzt erneut versuchen',synced:'Einkauf synchronisiert',offlineReady:'Offline – Änderungen werden lokal gespeichert.',offlineNeedsList:'Offline kann nur zu einer bereits vorhandenen Einkaufsliste hinzugefügt werden.'
};
const en={
  pending:'Not synced yet',syncing:'Syncing …',pendingCount:'{{count}} change is waiting to sync',pendingCount_other:'{{count}} changes are waiting to sync',failed:'Sync failed',failedHint:'Some changes could not be uploaded after several attempts.',retry:'Try again now',synced:'Shopping synced',offlineReady:'Offline – changes are saved on this device.',offlineNeedsList:'While offline, items can only be added to an existing shopping list.'
};

i18n.addResourceBundle('de','translation',{shoppingOffline:de},true,true);
i18n.addResourceBundle('en','translation',{shoppingOffline:en},true,true);
export default i18n;
