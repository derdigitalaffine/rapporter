# Offline-first implementation notes

## Existing code to reuse

- Keep the current handwritten service worker for app-shell/static asset caching, push, and update behavior.
- Evolve the current IndexedDB/offline-store work rather than layering generic `/api/*` response caching over private domain data.
- Use the existing PWA update manager and Playwright setup as integration points for offline/reload/update tests.

## Migration strategy

1. Introduce the common sync/data infrastructure without changing all screens at once.
2. Migrate Shopping first and remove its old snapshot-only mutation path only after the new path passes E2E coverage.
3. Migrate Tasks next, preserving domain workflow behavior through commands.
4. Migrate Calendar next, enforcing external-source read-only behavior.
5. Add live WebSocket wakeups only after HTTP delta sync is correct.
6. Remove obsolete fallback/snapshot code after each migrated domain has no remaining callers.

## Avoid

- Do not cache private `/api/*` responses in Cache Storage as the primary offline database.
- Do not implement separate online and offline write code paths.
- Do not let WebSocket payloads become a second synchronization protocol.
- Do not silently resolve same-field conflicts by last-write-wins.
- Do not delete IndexedDB during upgrades while pending outbox data exists.
- Do not make Redis availability a correctness dependency.
