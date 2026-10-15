# Sync status UI optimization — 2026-10-15

Refs #736 #578 #400 #435 #436.

Primary question: are my local changes confirmed by the server, and are live
updates connected? The previous single label conflated an empty local queue with
server reachability and did not expose WebSocket lifecycle. A cached historical
success is not current connection evidence.

The existing header control now has a primary sync/server state and a visible live
connection line. Its existing sheet uses compact semantic definition rows for
server, live, last success and local changes, followed by one manual check action.
Conflict review remains in the same canonical sheet. No nested-card hierarchy,
new component library, new navigation or duplicate data path is introduced.

- Existing surface/border/text/focus/status tokens retained; no color-only status.
- Primary controls retain 44px minimum touch targets.
- Small screens stack fact labels and values; desktop width stays bounded.
- Opening the sheet focuses Close; Tab is contained; Escape closes and restores
  focus. Facts use definition lists and the historical success uses a time element.
- New states/controls are localized for de/en/fr/nl/th.
- Browser regression captures 320/390/1440, server failure while navigator.onLine
  remains true, historical last-success display, keyboard closure and recovery.
- Local Chromium download is unavailable in this environment; final visual review
  uses the screenshots emitted by scoped offline-real CI. Native screenreader and
  physical browser zoom are not claimed from automated viewport checks.

Next owner-prioritized work: #738 family calendar subscriptions and additional iPhone
profile, reusing the canonical Calendar and shared Settings flow. #599 UI/CI
baseline repair remains queued afterward; existing domain ownership is retained.


Owner hotfix #744 supersedes the two-line changing header presentation: a constant
localized Sync label and static multicolor LED now carry quiet health. Routine
empty-queue HTTP checks preserve confirmed LED state; only meaningful reachability,
queue/conflict, live or freshness changes affect it. Accessible descriptions and
shape symbols supplement colors; the detailed canonical sheet/legend remains.
