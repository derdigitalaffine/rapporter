# Family Decision Core

Family Decisions are small reusable family polls. They are intentionally a focused primitive rather than a survey, messenger, or project-management system.

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

`context` is optional. A decision can exist without any feature-specific object. When a context is supplied, creation uses the canonical ContextLink service and is transactional: if the target is unavailable, cross-family, unsupported, or not linkable, neither the link nor the decision is committed.

Supported initial context types are Task, Note, Trip, Shopping List, Shopping Item, Pinboard Post, and Calendar Event. Context links never broaden the source object's ACL.

### Detail

`GET /api/decisions/<decision-uuid>/?family=<family-uuid>` returns the question, options, aggregate vote counts, the caller's current selection, open/closed state, permissions, and canonical context metadata when present.

A context-bound decision is visible only while its linked context is visible to the caller. For example, a decision linked to a private Note disappears from list/detail and from generic ContextLink queries after that caller's NoteShare is revoked. Unknown, foreign-family, or inaccessible IDs use neutral unavailable responses rather than revealing existence.

### Vote

`POST /api/decisions/<decision-uuid>/vote/`

```json
{
  "family": "<family-uuid>",
  "option_ids": ["<option-uuid>"]
}
```

Vote writes use **replace semantics**: the submitted option set atomically replaces all previous choices for the current membership. Sending an empty array removes the caller's vote. `single` decisions allow at most one selected option; `multiple` decisions allow multiple unique options from that decision. Guests are read-only. Votes cannot change after manual close or after `closes_at` has passed.

### Close

`POST /api/decisions/<decision-uuid>/close/`

```json
{"family": "<family-uuid>"}
```

The creator, family owner, or adult can close a decision. Closing is idempotent and does not delete votes or context metadata.

## Privacy and anonymity

Anonymous decisions still store the voting Membership internally so the service can enforce one coherent vote set per member and safely support vote replacement. The API deliberately does **not** serialize voter identities for anonymous decisions: option results contain aggregate counts only. The caller still receives `my_option_ids` so their own selection can be rendered without deanonymizing anyone else.

For non-anonymous decisions, option results may include each voter's membership UUID and family display name. This is family-private data and is returned only to active family members who can see the decision and, for context-bound decisions, the linked context.

## Notifications

The core does not emit per-vote notifications. Optional creation/end reminders are a later UX/prefs integration and must use the central notification preference system; vote events must not create notification floods.

## Extension rules

New domains should not add bespoke poll foreign keys. Prefer an allow-listed `decision.context` ContextLink adapter after defining the domain's visibility and lifecycle contract. A new relation must preserve the rule that the linked object's ACL remains authoritative and that losing context access removes visibility of the context-bound decision.
