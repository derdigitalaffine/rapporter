# Family Decision Core

Family Decisions are small reusable family polls. They are intentionally a focused primitive rather than a survey, messenger, or project-management system.

## User flows

The Decisions area supports four voting modes:

- **One option (`single`)** for a classic vote with one choice.
- **Several options (`multiple`)** when more than one answer may fit.
- **Ranking (`ranking`)** when all options should be ordered from most to least preferred. Ranking always submits a complete order; moving an option up or down is available with explicit buttons and does not depend on drag and drop.
- **Rating (`rating`)** for independent 1–5 ratings. Members may rate one or several options.

Contextual decisions use the same Decision objects and API as the central Decisions area. They do not create Shopping- or Trip-specific poll models.

### Shopping

A shopping list exposes **Vote together** next to the existing context action. The compact presets are:

- **Plan a purchase / Anschaffung planen** – starts as a ranking.
- **What should we eat? / Was wollen wir essen?** – starts as a single-choice vote.

The preset only pre-fills the question and voting mode; users can still edit the question, mode, and options before creating the decision. Closed decisions with a unique winner offer an explicit **Add winner to shopping list** action. This uses the canonical shopping quick-add endpoint, so an existing matching item is re-opened instead of silently duplicating it. Ties are never transferred automatically.

### Travel

A concrete Trip exposes the same contextual action in its existing FamilyOS planning section. Presets cover destination (ranking), accommodation (rating), and activities (multiple choice). The decision remains linked to the Trip through `decision.context`, and the Trip remains the authoritative object for travel visibility and lifecycle.

These contextual launchers are progressive disclosure: no extra decision data is loaded until the user opens the action.

## API

All endpoints require authentication and an active membership in the supplied family.

### Create and list

`GET /api/decisions/?family=<family-uuid>` lists up to 100 currently visible decisions.

`POST /api/decisions/` creates a decision:

```json
{
  "family": "<family-uuid>",
  "question": "Samstag oder Sonntag?",
  "mode": "single",
  "anonymous": false,
  "closes_at": null,
  "options": ["Samstag", "Sonntag"],
  "context": {"type": "trip", "id": "<trip-uuid>"}
}
```

`mode` accepts `single`, `multiple`, `ranking`, or `rating`.

`context` is optional. A decision can exist without any feature-specific object. When a context is supplied, creation uses the canonical ContextLink service and is transactional: if the target is unavailable, cross-family, unsupported, or not linkable, neither the link nor the decision is committed.

Supported initial context types are Task, Note, Trip, Shopping List, Shopping Item, Pinboard Post, and Calendar Event. Context links never broaden the source object's ACL.

### Detail

`GET /api/decisions/<decision-uuid>/?family=<family-uuid>` returns the question, options, aggregate vote counts, the caller's current selection, open/closed state, permissions, and canonical context metadata when present.

Each option also exposes `average_rank`/`my_rank` for ranking decisions and `average_score`/`my_score` for rating decisions. Values that do not apply remain `null`, keeping the response shape stable across modes.

The top-level `result` object is the canonical aggregate used by integrations. Its `metric` is `votes`, `average_rank`, or `average_score`; `leaders` contains all leading options, `is_tie` signals a tie, and `winner` is present only when exactly one option leads. Integrations must not invent a separate winner calculation or perform an automatic side effect from this field.

A context-bound decision is visible only while its linked context is visible to the caller. For example, a decision linked to a private Note disappears from list/detail and from generic ContextLink queries after that caller's NoteShare is revoked. Unknown, foreign-family, or inaccessible IDs use neutral unavailable responses rather than revealing existence.

### Vote

`POST /api/decisions/<decision-uuid>/vote/`

Single/multiple and ranking ballots use `option_ids`:

```json
{
  "family": "<family-uuid>",
  "option_ids": ["<option-uuid>"]
}
```

For `ranking`, `option_ids` is ordered from rank 1 downward and must contain every option exactly once. An empty array clears the ranking.

Rating ballots use `ratings`:

```json
{
  "family": "<family-uuid>",
  "ratings": [
    {"option_id": "<option-uuid>", "score": 5},
    {"option_id": "<option-uuid>", "score": 3}
  ]
}
```

Scores are integers from 1 through 5. An empty `ratings` array clears the caller's ratings.

Vote writes use **replace semantics**: the submitted ballot atomically replaces all previous choices for the current membership. `single` decisions allow at most one selected option; `multiple` decisions allow multiple unique options from that decision; `ranking` requires a complete ordered ballot; `rating` accepts independent scores for a subset of options. Guests are read-only. Votes cannot change after manual close or after `closes_at` has passed.

### Close

`POST /api/decisions/<decision-uuid>/close/`

```json
{"family": "<family-uuid>"}
```

The creator, family owner, or adult can close a decision. Closing is idempotent and does not delete votes or context metadata.

## Privacy and anonymity

Anonymous decisions still store the voting Membership internally so the service can enforce one coherent vote set per member and safely support vote replacement. The API deliberately does **not** serialize voter identities for anonymous decisions: option results contain aggregate counts/ranks/scores only. The caller still receives their own selection/rank/score so their ballot can be rendered without deanonymizing anyone else.

For non-anonymous decisions, option results may include each voter's membership UUID and family display name plus the applicable rank or score. This is family-private data and is returned only to active family members who can see the decision and, for context-bound decisions, the linked context.

## Notifications

The core does not emit per-vote notifications. Optional creation/end reminders are a later UX/prefs integration and must use the central notification preference system; vote events must not create notification floods.

## Extension rules

New domains should not add bespoke poll foreign keys. Prefer an allow-listed `decision.context` ContextLink adapter after defining the domain's visibility and lifecycle contract. A new relation must preserve the rule that the linked object's ACL remains authoritative and that losing context access removes visibility of the context-bound decision.

UI integrations must use the app-wide form primitives and progressive disclosure from #400/#223. They may pre-fill a contextual question or mode, but they still create the canonical Decision object and must require an explicit user action before writing a result into another domain.
