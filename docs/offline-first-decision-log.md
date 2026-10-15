# Offline-first decision log

Baseline decisions: local-first reads/writes; Shopping, Tasks, and native Calendar are writable offline; external calendar data is read-only offline; conflicts are field-aware; sync uses a per-family cursor and bidirectional `/api/sync/`; deletes are represented in a sync journal; client-generated UUIDs and idempotent mutation IDs are required; journal history is retained for 90 days before snapshot recovery; WebSockets only signal that sync is available; Django Channels, Redis, and ASGI provide live wakeups; one browser tab acts as sync leader; the handwritten service worker remains; IndexedDB is normalized and account/family scoped; explicit logout clears private local data; schema/protocol migrations preserve pending outbox work; rollout order is foundation, Shopping, Tasks, Calendar, live transport, robustness.

Any deviation should be documented before implementation.
