# Family Statistics metrics and privacy contract (#590)

Statistics is a tenant-private Premium/VIP read model, separate from #204 operational telemetry. It consumes canonical successful Action/Shopping domain mutations; it does not create tasks, routines or shopping items. No analytics SDK, clickstream, titles, notes, locations, document/message/care content or arbitrary metadata enters the contribution ledger.

## Metrics

- **Completed**: task/routine execution records and purchased shopping items. The total is explicitly an activity mix, never a universal effort/fairness score.
- **Organized**: task/routine creations, shopping items added and shopping lists created. Planning remains separate from execution.
- **Reopened**: task reopening actions; prior successful executions remain historical activity, not a current completion ratio. A deleted routine log is a correction and removes its execution from statistics.
- **Estimated effort**: task completion estimates only. Known-estimate completion count / all task completions is shown alongside minutes. Legacy estimates above 10,080 minutes are excluded from effort coverage and never block canonical completion. Actual duration is not silently mixed with estimates.
- **Actor coverage**: execution events with a valid actor membership / all executions. No task assignee or current TaskStatusEvent is interpreted as the completing actor.
- **Overdue now**: current visible incomplete tasks with due_at before now, explicitly a snapshot rather than a period completion rate.
- **Routine due/rate**: unavailable for historical periods without an immutable due/schedule basis. Never manufacture a denominator from today's adaptive interval. Routine executions and current schedule remain available.
- **Previous period**: immediately preceding equal-length local-date window. Percentage change is unavailable if the previous count is zero.

## Roles and ACL intersection

Every read requires active family membership AND statistics capability AND the relevant todo/shopping capability. No superadmin override grants access without membership. Owner/adult sees stable membership order and named contributions. Teen sees anonymous family aggregates and only their own named rows; member filters cannot select another person. Child sees only their own positive progress; guest has no access. Export is adult-only.

Gift/birthday/hidden task and shopping rows are excluded altogether, rather than risking aggregate leaks or multiplying rollup ACL states. Turning an existing entity private removes its previous contribution records. Deleted canonical entities remove associated statistics; a deleted item's prior gift visibility cannot safely be inferred. No sensitive care/health, expenses, GPS, Messenger, notes or documents adapter is enabled. Calendar's action is allowlisted for a future reviewed adapter but not collected or returned in V1.

## Attribution and retries

ActionDomainEvent / ActionCompletion from #594/#606 is the task/routine event contract. Completion signals can initially precede command attribution; one-time finalization within the command window updates the same stable completion bucket and recomputes rollups transactionally. Stable keys use task ID + completion timestamp, RoutineLog ID, ShoppingPurchaseEvent ID and canonical create event ID. Retries of the same successful mutation do not increment again. Historical task completion without a proven actor contributes only to the family total. Reopening and a new completion is a new successful execution.

Backfill consumes retained canonical Action completion events, RoutineLog.done_by and ShoppingPurchaseEvent.purchased_by. Shopping events are imported only while their source item's non-private visibility can still be proved. Current completed tasks without canonical actor history are imported as unknown, not assigned to assignee. Backfill never imports historical planning from the migration-time Action mirror creation.

## Retention and deletion

Collection and reads stop when statistics entitlement is revoked. Data already collected stays subject to the same retention/privacy rules; upgrading does not infer actors for the intervening period. `STATISTICS_RETENTION_DAYS` defaults to 730 days, with a minimum of 730 to support 365-day comparisons. Both raw events and rollups use this bound; no infinite aggregate retention.

The existing `sync_integrations` scheduler prunes expired contributions and rebuilds affected families. `python manage.py rebuild_family_statistics` additionally performs an explicit deterministic repair. `--family=<uuid>` scopes maintenance; `--backfill` imports only the reviewed sources above. It is safe to rerun. Family timezone changes rebuild local-day buckets, including DST. Family deletion cascades all rows. Membership/account deletion clears both user and membership attribution, recomputes anonymous buckets, and rejoining never relinks the previous history, including later canonical completion edits (a finalized-attribution privacy tombstone survives anonymization). Stored IDs contain no content and API responses never reconstruct deleted content.

## Performance and migrations

Overview reads a bounded daily rollup range, not raw events or one domain query per card/member. Drill-downs paginate 50 content-free events. Rebuild performs database grouping and bulk insertion. Family-row locks serialize recording/recomputation; F-expression increments protect daily counts. Indexed family/time, actor/time, domain/time and entity lookups; unique family/idempotency and daily member/domain/action/date constraints.

Apply additive statistics/entitlement migrations normally; no legacy table is rewritten. Run a controlled backfill after deployment, then daily retention maintenance. Rollback disables statistics wiring/capture/UI first, preserving legacy functionality; retain new tables until privacy/retention cleanup is complete. No destructive legacy migration.

## Product integration

Statistics is a read-only page under More, using #577 feature/navigation and the existing active family. No root Create action, Today widget, task, calendar occurrence, pin, context link, document attachment, search indexing or notification is generated merely by viewing statistics. Drill-down links open canonical domains. Offline keeps only the mounted, already-authorized in-memory snapshot with a visible stale timestamp; family switch, downgrade and access failure discard it. No private persistent/offline statistics cache.

UI question: “What did we do and organize, and how did it change?” Four primary summaries, followed by progressive domain/member filters and accessible chart/table alternatives. No ranking, gamification or psychological interpretation.
