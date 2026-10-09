# Family workflows: researched design decisions

Research checked 2026-10-10. Store ratings vary by region and time; a high aggregate rating does not establish that an individual feature caused it. The following decisions combine documented product behaviour, concrete user feedback and this application's requirements.

## Shopping in a store (#132)

AnyList's US App Store listing currently shows 4.9/5 across roughly 81K ratings. User reviews specifically value shared lists and reliability. Its official help documents item tapping, hidden completed items, restore flows and protection against accidental taps.

- https://apps.apple.com/us/app/anylist-grocery-shopping-list/id522167641
- https://apps.apple.com/us/app/anylist-grocery-shopping-list/id522167641?platform=iphone&see-all=reviews
- https://help.anylist.com/articles/getting-started/
- https://help.anylist.com/articles/show-hide-completed-items/
- https://help.anylist.com/articles/cross-off-items/

FamilyOS chooses a dedicated compact checklist, whole-row targets, a separate details button, a short confirmation before removal and Undo. The existing offline queue remains the only write path. A visible online session refreshes remotely without erasing local pending writes. Density is measured at 390×844; comfort is preserved by 48px rows and 44px details targets. No store floor-plan or recipe workflow is added.

## Optional workflows (#123)

Todoist documents interchangeable list/board views and section-based organization. Its mobile help includes changing layouts and moving tasks without relying exclusively on drag gestures.

- https://www.todoist.com/de/help/todoist/features/use-the-board-layout-in-todoist-AiAVsyEI
- https://www.todoist.com/help/todoist/get-started/get-started-with-todoist-OgNNJR

FamilyOS keeps simple lists as default and enables workflows separately per list. The same tasks retain assignee, due date, priority, effort and tags. Phone boards use status tabs and a vertical list; larger displays use columns. A status selector supplies a keyboard/touch alternative to dragging. Status transitions and completion share one server invariant and a list lock; sorting positions and history persist independently.

## Birthday preparation (#122)

hip's US App Store listing shows 4.7/5 across about 18K ratings. Its description combines countdowns, customizable advance reminders, notes, calendar sync and grouped privacy. Reviews mention reliable remembering and contact context.

- https://apps.apple.com/us/app/hip-birthday-reminder-app/id401949944
- https://apps.apple.com/us/app/id401949944?see-all=reviews

FamilyOS uses a single canonical birthday, an upcoming list, virtual all-day calendar occurrences and recurring 21/7/1/0 day reminder stages. A per-year gift plan links real task/shopping records; completing the gift task updates readiness. Early preparation reminders stop once ready. Surprise content is filtered by the server for the birthday person, including dashboard counts, direct access and notifications. Feb29 is explicitly projected to Feb28 in non-leap years.

## Routines (#140)

Streaks documents selectable completion frequencies, large completion interactions, reminders, statistics, widgets and undo. Strides documents target-based tracking and progress. These are relevant mechanisms; FamilyOS does not equate streak length with success or punish missed days.

- https://streaksapp.com/
- https://apps.apple.com/us/app/streaks/id963034692
- https://www.stridesapp.com/

Name-only creation stays valid. Optional count/period goals work immediately before historical learning. Actual elapsed intervals carry recency weights; suspicious rapid repeats do not distort learned cadence. The explicit goal caps the next expected interval, so repeated late runs never silently weaken the user's wish. The UI distinguishes target, actual count, learned interval and next prediction. Logs have actors, idempotency keys, a paginated history and Undo. Reminders run in local daytime, respect personal preferences/snooze, and are bounded to one delivery per cycle and per24 hours; transport failures stay retryable.

## Operational verification

API tests cover family isolation, birthday privacy, occurrence dates and reminder idempotency; workflow terminal/completion invariants and sorting; routine goal validation, cadence, logging retries, permissions and reminders. Browser tests cover mobile density, offline Undo/reconnect, accessible status changes, history, reload and discovery. Screenshot baselines change only for intentionally changed visible UI and are inspected before acceptance.
