# Quiz duel and Connect Four extension

Issue #537 extends the canonical Family Games domain from #509 under the coordination rules in #223. The extension reuses `GameMatch`, `family.Membership`, the existing notification core, task stakes, Games Hub, and Today summary; it does not add parallel identity, challenge, notification, or widget systems.

## Quiz duel

`quiz` uses the normal `pending → active → finished` match lifecycle. A challenge stores a round count from 3 through 7 and one of three server-validated modes:

- `mixed` — general knowledge;
- `physics_expert` — very high university-level theoretical/analytical physics;
- `chemistry_expert` — very high university-level theoretical/analytical chemistry.

Questions are persisted in `games.QuizQuestion`. Each row contains German and English prompts/options, the authoritative correct option, and an optional explanation. The initial additive migration seeds at least seven questions per mode. Expert chemistry content deliberately stays conceptual and analytical; it contains no dangerous synthesis recipes, operating parameters, procurement guidance, or other actionable hazardous-lab instructions.

For each round the server creates exactly one `QuizRound` and binds one question to both players. A participant may submit one answer. Until both answers exist, participant payloads expose the prompt/options and only submission booleans; they do **not** expose either selected option, the correct index, correctness, or the explanation. After both submissions the server resolves correctness and may reveal the round solution. After the configured final round, most correct answers wins; equal scores produce a draw.

Question selection, answer validation, scoring, lifecycle transitions, task-stake application, and notifications are server authoritative. Clients cannot supply a question, correct answer, score, or winner.

Endpoint: `POST /api/games/<match>/quiz/answer/` with an integer `answer` option index.

## Connect Four

`connect_four` uses a 7-column × 6-row board. The challenger has the first move after acceptance. Every move is stored as a normalized `ConnectFourMove` with server-computed row and sequence.

The server validates participant access, active state, current turn, column range, and available capacity. A client supplies only the target column; it cannot choose the row or submit a board. After each valid move the server checks horizontal, vertical, and both diagonal directions. Four or more connected discs finish the match for that player; a 42-move full board without a winning line is a draw. Otherwise the turn passes to the other participant.

Endpoint: `POST /api/games/<match>/connect-four/drop/` with integer `column` in the range 0–6.

## Privacy and projections

The existing participant boundary remains unchanged: only the two active-family participants can retrieve or mutate a match. Quiz correct answers and submitted choices are secret until round resolution. Connect Four has no hidden board state. Notifications contain lifecycle text and deep links only, never quiz answers or solutions.

The Games list/detail and bounded Today summary use the same serializer and therefore inherit the same privacy guarantees. The Today consumer treats Quiz and Connect Four like the existing games for invitations/actionability without duplicating their internal state.

## UI and accessibility

The Games Hub presents all four game types as explicit cards with concise descriptions. Active cards elevate actionable turns. Quiz uses large answer targets, score/round context, hidden-answer waiting state, and expandable resolved-round explanations. Connect Four uses a compact responsive board plus seven 44px-or-larger drop controls, keyboard-operable native buttons, and labelled grid cells.

The existing task-stake consent flow remains available to all four games. DE/EN copy is supplied for the new Hub interactions. The 390×844 layout stays single-column without horizontal page overflow.

## Rollout and rollback

Migration `0003_quiz_connect_four` is additive: it widens the game-type field, adds quiz configuration to `GameMatch`, creates quiz question/round and Connect Four move tables, and seeds the initial question bank. Existing RPS, Battleship, task-stake, Today, and notification rows remain valid.

For an application rollback, disable creation/action UI and endpoints for the two new game types first. The additive tables can remain in place while old application code runs. A later cleanup migration may remove them only after historical/audit requirements are resolved.
