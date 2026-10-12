# Family games contract

This document defines the additive FamilyOS games slice introduced by #509 under the product and architecture rules in #223.

## Scope

Family members can challenge another active member of the same family to one of two turn-based games:

- Rock · Paper · Scissors (`rps`) with a configured round count from 1 through 5.
- Battleship (`battleship`) on a 10×10 board with the fleet sizes `5, 4, 3, 3, 2`.

Games are intentionally reachable from **More** instead of adding another primary navigation destination. The optional Today widget is registered through the existing versioned Today widget registry and consumes the games summary API.

## Identity and authorization

`family.Membership` remains the only player identity. Games do not create a parallel player/account model.

- Challenger and opponent must belong to the same active `family.Family`.
- Only the two match participants can retrieve or mutate a match.
- Authorization, phase transitions, turn ownership, fleet validation, RPS resolution, and win resolution are enforced on the server.
- Cross-family or third-party access returns an unavailable/not-found result instead of exposing match existence.
- UI visibility is convenience only and is never the authorization boundary.

## Lifecycle and API

Match states are `pending`, `active`, `finished`, `declined`, and `cancelled`.

Endpoints are additive under `/api/games/`:

- `GET /api/games/?family=<uuid>` — participant-scoped matches for one active family.
- `POST /api/games/` — create a challenge.
- `GET /api/games/<match>/` — participant-scoped detail.
- `POST /api/games/<match>/accept/`
- `POST /api/games/<match>/decline/`
- `POST /api/games/<match>/cancel/`
- `POST /api/games/<match>/rps/choice/`
- `POST /api/games/<match>/battleship/fleet/`
- `POST /api/games/<match>/battleship/fire/`
- `GET /api/games/summary/?family=<uuid>` — bounded Today-widget projection.

The API follows the repository convention of a stable `{ "code": "..." }` error body for domain errors.

## Rock · Paper · Scissors privacy

A player can submit exactly one choice per round. Until both participants have submitted, the API exposes only submission booleans and returns neither the local nor remote choice. Once both choices exist, the round is resolved and both choices become visible to both participants.

The match always runs exactly the configured number of rounds (1–5). Each resolved round can be won by either participant or tied. After the final configured round, the player with more won rounds wins; equal win counts produce a match draw.

## Battleship privacy and turn contract

Each participant submits one fleet containing exactly the lengths `5, 4, 3, 3, 2`. Server validation requires every ship to be contiguous, horizontal or vertical, inside the 10×10 board, and non-overlapping.

The shooting phase starts only after both fleets are confirmed. The challenger has the first shot and turns alternate after every valid shot. A coordinate may be fired at only once for a target board.

The participant payload contains:

- the caller's own confirmed ship coordinates;
- whether the opponent has confirmed a fleet;
- public shot coordinates and their `miss`, `hit`, or `sunk` result;
- sunk ship size where applicable.

It never contains an opponent's unhit ship coordinates. The match finishes as soon as every cell in the target fleet has been hit.

## Notifications

Games reuse `notifications.services.record_notification`; there is no games-specific delivery or preference pipeline. Notifications contain only human-readable lifecycle information and the match deep link, never RPS choices or ship coordinates.

Events:

- `games.challenge` — new challenge for the opponent;
- `games.started` — challenge accepted / game started;
- `games.turn` — actionable RPS turn, fleet setup, or Battleship turn;
- `games.finished` — final result for both participants.

Duplicate rejected mutations (for example a second RPS choice) do not emit another notification.

## Today widget

The optional `games` widget is registered in `TodayWidgetRegistry` without changing the layout schema version. Existing saved layouts are expanded losslessly with the new widget hidden by default. Users can add it from the existing widget library.

The widget has explicit loading, error/retry, actionable, and empty states. It links back to the Games hub and shows only the current user's participant-scoped summary.

## Accessibility and responsive behavior

The Games hub uses native form controls and buttons, explicit status/alert regions, labelled 10×10 grid cells, visible focus behavior, and minimum 44px primary actions. The layout collapses to one column on narrow screens and the board grid uses fractional cells so the 390×844 target does not require horizontal scrolling.

German and English UI copy is provided for the Games hub and Today widget.

## Persistence, rollout, and rollback

The `games` Django app owns additive tables for matches, RPS rounds, Battleship boards, and shots. Existing family, notification, and Today persistence is referenced rather than duplicated.

Rollout order:

1. deploy the additive migration;
2. deploy backend/API and frontend together;
3. clients discover the optional hidden Today widget through the existing registry expansion.

Rollback is safe at the application layer because existing domains do not depend on games tables. Disable/remove the Games routes and UI first; the additive tables can be retained for a later re-enable or removed in a follow-up migration after confirming no rollback data is required.
