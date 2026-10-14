# Offline-first privacy boundaries

- Private domain data stays in IndexedDB, not generic service-worker `/api/*` caches.
- Local records are namespaced by account and family.
- Explicit logout/account switch clears account-scoped entities, outbox, conflicts, sync state, and private cached metadata.
- Server authorization is rechecked for every sync request and family scope.
- Client-generated IDs and mutation IDs never grant authorization.
- Authentication expiry pauses network sync without deleting local offline work.
- External calendar ownership/family checks remain enforced.
