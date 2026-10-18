# Shopping checkout

The shopping checkout is part of the canonical `ShoppingSession` flow. It does not create a separate purchase, presence, store, or expense domain.

## Collaborative completion

When more than one person is currently active in the same shopping session, checkout distinguishes two actions:

- **My shopping is done** leaves only the current user's participation. The shared shopping session and shopping list stay active for the other participants.
- **Finish the shared shopping trip** completes the canonical shopping session for everyone. When active peers are present, the checkout requires an explicit confirmation before this action is enabled.

Presence is intentionally short-lived. Participants whose `last_seen_at` is older than the server presence window are not treated as active peers, so stale or abandoned clients do not block group completion indefinitely.

## Concurrent changes and retry

The checkout review reads the session `revision`, backed by the existing shopping activity sequence. A group completion may send that revision as `expected_revision`.

If the shopping session changed after the review was opened, the server returns `409 stale_session` with the current revision/session. The client returns to the review state and requires the user to review the finish action again.

If the active peer set requires confirmation, the server returns `409 active_peers_confirmation_required` unless the caller explicitly confirms the group finish. The client refreshes the visible peer list and requires confirmation again.

A retry against an already completed session is idempotent: the existing immutable completion snapshot is returned and is not replaced by a newer store, open-item policy, revision, or peer state.

## Offline behavior

Personal exit and group completion both use the existing shopping mutation flush before checkout. If pending shopping mutations cannot be confirmed by the canonical server, checkout is not presented as completed. The user can retry after synchronization succeeds.

## Privacy and access

All session lookup and completion remains tenant-bounded by the existing shopping-list visibility rules. A guessed shopping-list or session id from another family is not exposed. Participant presence is used only to coordinate the active shared shopping session; it is not a movement or location history.

Related: #781, #779, #223.
