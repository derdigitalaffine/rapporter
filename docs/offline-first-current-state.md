# Offline-first current state

Rapporter already has a hand-written service worker and initial IndexedDB shopping/fallback structures. The offline-first program evolves those foundations into a normalized local domain store and synchronization engine. The existing service worker remains responsible for the static app shell; private domain data moves through IndexedDB and `/api/sync/` rather than generic API response caching.
