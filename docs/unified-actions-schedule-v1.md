# Unified Actions Schedule Contract v1

Related: #594, ADR-0002.

`action-schedule-v1` is the server-owned temporal contract shared by Unified Actions, adaptive prediction, Today ranking, reminders, widgets and later automation adapters.

It deliberately separates four concerns:

1. **intent** — what the family explicitly configured;
2. **observations** — what actually happened;
3. **prediction** — what the server currently expects;
4. **proposal** — a suggested schedule change when observed behavior is stably different.

A prediction must never overwrite intent just because it is confident.

## Versioning

Every schedule payload includes:

```json
{
  "version": "action-schedule-v1",
  "timezone": "Europe/Berlin"
}
```

A future incompatible contract must use a new version. Stored schedules must remain parseable after deployment rollback.

## Scheduling modes

`mode` is one of:

- `static` — explicit user schedule is authoritative. Learning may be shown as insight only.
- `learning` — incomplete intent may be filled by server prediction as confidence grows.
- `adaptive` — explicit schedule is authoritative at execution time, but a stable material deviation may create an explainable proposal that the user can accept/reject. Optional per-Action auto-adaptation can only affect fields explicitly marked flexible.

Default for newly inferred Actions created via “Ich habe gerade …” is `learning` unless product settings choose otherwise.

## Recurrence

Recurrence is normalized and must not depend on a browser-specific natural-language parser.

Supported v1 shapes:

### Once

```json
{"frequency":"once","date":"2026-10-20"}
```

### Daily / every N days

```json
{"frequency":"daily","interval":3}
```

### Weekly

```json
{
  "frequency":"weekly",
  "interval":1,
  "weekdays":["MO","WE","FR"]
}
```

### Monthly

By day number:

```json
{"frequency":"monthly","interval":4,"month_days":[15]}
```

By nth weekday:

```json
{
  "frequency":"monthly",
  "interval":4,
  "nth_weekdays":[{"weekday":"TH","ordinal":2}]
}
```

This represents use cases such as “alle 4 Monate am zweiten Donnerstag”. `ordinal` is one of `1..5` or `-1` for last.

### Yearly

```json
{
  "frequency":"yearly",
  "interval":1,
  "months":[3,9],
  "month_days":[1]
}
```

The implementation may internally map to RFC-5545-like semantics, but arbitrary raw RRULE text is not the sole canonical API because FamilyOS also needs typed flexible windows, learning policy and explainability.

## Day/time policy

Each recurrence can have zero or more local-time segments:

```json
{
  "segments":[
    {
      "weekdays":["MO","TU","WE","TH","FR"],
      "preferred_time":"18:00",
      "window":{"start":"17:00","end":"19:30"}
    },
    {
      "weekdays":["SA"],
      "preferred_time":"14:00",
      "window":{"start":"12:30","end":"16:00"}
    }
  ],
  "excluded_weekdays":["SU"]
}
```

Rules:

- local wall-clock values are interpreted in `timezone`;
- `preferred_time` may exist without a window;
- a window may exist without a preferred time;
- no time segment means “day-level only”, not midnight;
- exclusions are explicit hard intent and outrank learned absence;
- multiple segments for the same weekday are allowed only after the implementation explicitly supports disjoint windows; initial UI may restrict to one segment per weekday.

## Exceptions

Date-specific exceptions are explicit and versioned:

```json
{
  "exceptions":[
    {"date":"2026-12-27","kind":"skip"},
    {
      "date":"2027-01-03",
      "kind":"override",
      "preferred_time":"12:00",
      "window":{"start":"10:00","end":"14:00"}
    }
  ]
}
```

An exception never rewrites the base recurrence.

## Flexible parts and auto-adaptation

An adaptive schedule can declare which fields may be auto-adjusted after explicit opt-in:

```json
{
  "adaptation":{
    "enabled":true,
    "auto_apply":false,
    "flexible_fields":["preferred_time","window"]
  }
}
```

Hard recurrence fields (e.g. explicit `excluded_weekdays`) are not auto-modified unless that field is explicitly flexible in a future contract version.

## Observation contract

Scheduling observations are derived from immutable/append-only execution events where possible.

Minimum server feature vector per occurrence:

- UTC `occurred_at`;
- family-local date;
- local weekday;
- local minute-of-day;
- actor when known;
- actual duration when supplied;
- source;
- planned occurrence reference when one exists.

Scheduling does not require notes, message text, document content, GPS, clickstream or app-usage duration.

Missing observations do **not** equal an explicit exclusion. For example, “no Sunday completions” may support a suggestion only with sufficient history; it may not silently become `SU` excluded.

## Prediction response

Server prediction uses a stable shape:

```json
{
  "version":"action-prediction-v2",
  "status":"learning",
  "expected_at":"2026-10-17T14:00:00+02:00",
  "window_start":"2026-10-17T12:30:00+02:00",
  "window_end":"2026-10-17T16:00:00+02:00",
  "confidence":0.82,
  "sample_count":11,
  "basis":["manual_recurrence","weekday_history","completion_time"],
  "explanation":{
    "key":"weekday_time_pattern",
    "weekday":"SA",
    "typical_time":"14:00",
    "typical_range":{"start":"13:25","end":"14:40"}
  },
  "suggested_schedule_change":null
}
```

The UI localizes explanation keys; the server does not return opaque prose as the only explanation.

## Learning requirements

Initial implementation requirements:

- calculate in the family timezone;
- use robust estimators so individual outliers do not dominate;
- maintain separate weekday time profiles when evidence supports them;
- keep cadence estimation separate from time-of-day estimation;
- expose low confidence rather than manufacture precision;
- handle midnight-wrap patterns correctly;
- test DST spring-forward and fall-back transitions;
- never use future events to score historical predictions in tests;
- all thresholds are server-side constants/settings and covered by tests.

A reasonable initial threshold is at least 3 observations for a weekday-specific time estimate and more evidence for a schedule-change proposal. Exact constants belong in implementation code, not this API contract.

## Proposal response

A material stable deviation may produce:

```json
{
  "suggested_schedule_change":{
    "proposal_id":"uuid",
    "kind":"weekday_preferred_time",
    "current":{"weekday":"SA","preferred_time":"18:00"},
    "proposed":{"weekday":"SA","preferred_time":"14:00"},
    "confidence":0.91,
    "sample_count":9,
    "reason_key":"stable_schedule_deviation"
  }
}
```

Feedback is explicit:

- accept;
- reject;
- dismiss/snooze if later required.

Rejecting a materially identical proposal is persisted as feedback so it is not immediately re-suggested.

## Calendar-aware planning

Calendar-aware movement is optional and controlled by settings.

When enabled it may move a **suggested** time only inside an allowed flexible window. It may not move a static exact time. The scheduling service should need Busy/Free-style data only; calendar title/body content is not required.

Prediction explanation must expose calendar adjustment as a distinct basis/reason.

## Waste / external event occurrences

External domain events may produce an executable Action occurrence without creating a new unrelated Task each cycle.

Example waste widget action:

`Biotonne · morgen 06:00  [Tonne rausgestellt]`

The button records an idempotent Action occurrence linked to the relevant event/context. The waste event remains canonical in its own domain.

## Compatibility adapters

Before Action is canonical, adapters translate legacy data conservatively:

- Task `due_at` → single due/once intent;
- Task `recurrence` → translate only patterns that can be losslessly represented; otherwise retain legacy recurrence and mark adapter-only;
- Routine target cadence → cadence/prediction input, without inventing weekday exclusions;
- RoutineLog → occurrence observation;
- existing routine prediction remains available as fallback until `action-prediction-v2` reaches parity.

No backfill may reinterpret ambiguous legacy recurrence strings without an explicit safe mapping.

## Test vectors

Required contract fixtures include at least:

1. Mon–Fri preferred 18:00, Saturday preferred 14:00, Sunday excluded.
2. Every Monday with no exact time.
3. Every 4 months on second Thursday.
4. Monthly last weekday variant.
5. Day-level recurrence with no midnight artifact.
6. Spring-forward day with nonexistent local clock time.
7. Fall-back day with ambiguous local clock time.
8. Static schedule with observations far away: prediction insight allowed, no mutation.
9. Adaptive schedule with stable material deviation: proposal generated.
10. Rejected proposal: no immediate identical re-proposal.
11. Sparse history: remains learning/low confidence.
12. Missing Sunday history: does not become exclusion by itself.