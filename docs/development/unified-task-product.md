# Unified Task Product

Refs #770 under #594/#223. One user-facing task/action workflow, not another
Task/To-do domain. `todo`, `tasks` and `routines` resolve to the same workspace;
old IDs and deep links remain compatibility entry points. Existing list/board
management and legacy routine editing remain adapters inside the product.

Task and its existing Action mirror are one logical object during the agreed
#594 migration. This delivery does not claim physical table consolidation or
remove RoutineLog, legacy IDs, APIs, automations or historical attribution.
Action-primary cutover still requires deployed shadow parity and rollback
evidence. No React Router runtime is added; #755 retained Navigation Service.

`TaskSerializer.action_schedule` exposes existing Action schedule metadata and
accepts its normalized contract on the existing Task create/update endpoint.
Both writes are transactional. Sync invokes the same serializer, includes this
field in snapshots/conflicts, and retains existing mutation receipts/client IDs.
No schema migration, second outbox or separate create endpoint is needed.

The create dialog reuses TaskEditor/FamilySheet and shared scheduling controls.
Existing-action hints are suggestions only; a failed optional search never
blocks creation. Dates, assignments and recurring/adaptive rules are explicit.
The normal task endpoint still owns tenant/list/assignee/workflow validation.

New UI capture sends `create_kind: task`; old clients omitting it retain their
legacy routine behavior. Both consume existing ActionCapture/ActionCompletion
receipts. Capture retries return the typed action ID so undo also works after
a lost response. Changed title/kind with the same capture key is rejected.
Recurrence completion includes quarterly rules and returns the current cycle.

Workspace reads all pages, includes undated work, scopes completed history
separately, rejects foreign pagination URLs and discards stale view/family
responses. Background mutation refresh preserves mounted rows. Search and
filters never authorize data or infer assignment from private content.

Validation: local Node/build/bundle/PostgreSQL tests; browser/Axe/viewport/PWA
checks remotely in Actions only. Native iOS/Android keyboard, AT and 200% zoom
remain separate #753 acceptance. No emulated result is presented as physical.

Rollback: revert UI bindings and additive serializer/capture field consumers.
Existing tasks, schedules, completion history and legacy clients remain valid;
no data migration or destructive rollback is necessary.
