# Pinboard stable adapter keys

Issue #219 moves Pinboard references from historical UI/card `kind` values to stable technical adapter keys without changing canonical source domains or ACL ownership.

## Canonical keys

| Canonical adapter key | Legacy `BoardPost.kind` |
| --- | --- |
| `calendar_event` | `event` |
| `task` | `task` |
| `note` | `note_ref` |
| `shopping_item` | `shopping` |
| `routine` | `routine` |
| `shopping_list` | `shopping_list` |
| `trip` | `trip` |
| `document` | `document` |

`BoardPost.kind=note` remains a native Pinboard note and is deliberately **not** the Note-domain adapter. The separate `adapter_key=note` removes that historical ambiguity.

## Expand → Migrate → Cutover

1. **Expand:** migration `0220_pinboard_adapter_keys` adds nullable-by-behavior/blank `BoardPost.adapter_key` while preserving `kind` and `target_id`.
2. **Migrate:** the same migration idempotently backfills only reference rows that have a target. Native note/photo rows keep an empty adapter key.
3. **Cutover:** the PinAdapter registry is keyed by the canonical values above. Reads prefer `adapter_key` and fall back to legacy `kind` only when the new field is empty. New canonical writes persist both `adapter_key` and the compatible legacy `kind`; old clients that still submit `kind` are canonicalized server-side.
4. **Contract (later):** removal of the compatibility field/path is intentionally not part of #219. It requires a separate compatibility decision after deployed clients have moved to `adapter_key`.

## ACL and lifecycle

Adapter keys never grant access. Every board read still resolves the canonical target through its domain-owned visibility rules. Deleted or no-longer-visible targets continue to render the neutral unavailable state; archived lifecycle rules remain adapter-owned. No title/body snapshot is copied into the pin row.

## Rollback

Before any future Contract phase, rollback is safe: the reverse migration clears `adapter_key` and then removes the field, while the legacy `kind` + `target_id` identity remains intact. Runtime dual-read means rolling application upgrades can read rows that have not yet been backfilled.
