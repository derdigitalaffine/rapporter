# Family games contract

This document defines the additive FamilyOS games slice introduced by #509 under the product and architecture rules in #223. Issue #513 extends that slice with an optional, explicitly consented task-assignment stake.

## Scope

Family members can challenge another active member of the same family to one of two turn-based games:

- Rock · Paper · Scissors (`rps`) with a configured round count from 1 through 5.
- Battleship (`battleship`) on a 10×10 board with the fleet sizes `5, 4, 3, 3, 2`.

Games are intentionally reachable from **More** instead of adding another primary navigation destination. The optional Today widget is registered through the existing versioned Today widget registry and consumes the games summary API.

A challenge can optionally carry a task-assignment stake. The task remains a canonical `family.Task`; games never copy task title, completion state, assignee truth, or task permissions into a second task model.

## Identity and authorization

`family.Membership` remains the only player identity. Games do not create a parallel player/account model.

- Challenger and opponent must belong to the same active `family.Family`.
- Only the two match participants can retrieve or mutate a match.
- Authorization, phase transitions, turn ownership, fleet validation, RPS resolution, and win resolution are enforced on the server.
- Cross-family or third-party access returns an unavailable/not-found result instead of exposing match existence.
- UI visibility is convenience only and is never the authorization boundary.
- A staked task must be an open canonical task in the same family and must be visible to both participants.

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

## Consented task-assignment stakes

Task assignment is an optional contract on top of an otherwise normal game. Standalone games continue to work without a task stake.

A challenger creates a binding stake by sending a `task_assignment` object with:

- `task` — canonical `family.Task` UUID;
- `rule` — `winner` or `loser`;
- `confirmed: true` — explicit challenger consent to the exact task, opponent, game and rule.

The opponent sees the same task and rule before accepting. A staked challenge can enter `active` only when the opponent sends `task_assignment_confirmed: true`. Ordinary non-staked matches do not require this flag.

The stake stores only coordination metadata: the task relation, the deterministic winner/loser rule, both consent timestamps, the assignee snapshot at challenge creation, and the final application/invalidation result. `family.Task.assignee` remains the only assignment truth.

### Automatic assignment after a valid result

When either game reaches its canonical `finished` state, the server processes the stake in the same database transaction as the finish:

1. lock the stake and canonical task;
2. verify both consent timestamps;
3. verify task/family/participant availability;
4. verify the task assignee still equals the snapshot accepted for the duel;
5. resolve `winner` or `loser` to the corresponding participant user;
6. write that user to the canonical `Task.assignee` exactly once.

The operation is idempotent. Re-reading a match or retrying around an already processed result cannot apply a second assignment.

A task is **not** changed when the game is declined/cancelled, ends in a draw, lacks consent, becomes unavailable, or has been reassigned after the stake was created. In the reassignment case, the later explicit task change wins and the duel outcome is recorded as invalidated rather than silently overwriting it.

The participant payload exposes only safe task-assignment state (`pending_consent`, `ready`, `applied`, `draw`, or `invalidated`) and user/task identifiers needed by the family UI. It never includes RPS choices before resolution or Battleship fleet secrets.

### Creating a new task from the Games hub

The Games hub can use either an existing open task or create a new normal task through the existing `/api/tasks/` endpoint before creating the challenge. This deliberately reuses the canonical task creation path rather than giving the games domain a second task-creation model.

If task creation succeeds but challenge creation subsequently fails, the newly created object remains a normal task and is selected for retry; the client does not silently delete canonical user data as compensation.

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

Task stakes do not add a parallel notification pipeline. The existing challenge/start/finish notifications lead to the participant-scoped game detail, where the task and stake rule are rendered from the safe game payload.

## Today widget

The optional `games` widget is registered in `TodayWidgetRegistry` without changing the layout schema version. Existing saved layouts are expanded losslessly with the new widget hidden by default. Users can add it from the existing widget library.

The widget has explicit loading, error/retry, actionable, and empty states. It links back to the Games hub and shows only the current user's participant-scoped summary.

## Accessibility and responsive behavior

The Games hub uses native form controls and buttons, explicit status/alert regions, labelled 10×10 grid cells, visible focus behavior, and minimum 44px primary actions. The layout collapses to one column on narrow screens and the board grid uses fractional cells so the 390×844 target does not require horizontal scrolling.

The task-stake flow uses native selects, text input and checkbox consent. The task title, deterministic rule and current assignment are visible before consent; the accept action for the opponent is explicitly labelled as accepting both task and duel.

German and English UI copy is provided for the Games hub and Today widget.

## Persistence, rollout, and rollback

The `games` Django app owns additive tables for matches, RPS rounds, Battleship boards, shots, and the one-to-one `GameTaskAssignment` coordination record. Existing family, task, notification, and Today persistence is referenced rather than duplicated.

Rollout order:

1. deploy the additive migration;
2. deploy backend/API and frontend together;
3. clients discover task stakes through the existing Games hub; standalone games remain compatible;
4. the optional Today widget continues to use the same summary endpoint and receives the safe task-assignment projection additively.

Rollback is safe at the application layer because the canonical task remains `family.Task`. Disable/remove task-stake creation in the Games UI/API first; existing stake rows can remain as historical coordination data. Removing the additive table should only happen in a later migration after confirming no rollback/audit data is required.
