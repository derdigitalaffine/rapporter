# FamilyOS Agent Coordination Contract

This repository is developed by humans and multiple fast, parallel coding agents. GitHub is the coordination plane. Do not create a second private planning system that other contributors cannot see.

## Authority order

1. **#223** is the central roadmap/control issue for cross-cutting priorities, gates, and architecture conflicts.
2. The **work issue** owns scope, acceptance criteria, and the active claim.
3. The **pull request** owns the concrete implementation and review discussion.
4. `CONTRIBUTING.md` and `docs/development/agent-coordination.md` define the shared workflow.

If instructions conflict, stop expanding scope and surface the conflict in the relevant issue. Cross-cutting conflicts belong in #223.

## Mandatory pre-flight before coding

Before changing code for an issue:

1. Read the latest relevant section and recent comments in #223.
2. Read the complete target issue and its comments.
3. Search open issues with label `in progress`.
4. Search open pull requests, especially those touching the same domain/files/contracts.
5. Check whether a canonical FamilyOS core already owns the problem. Never create a parallel Task, Calendar, Document, Note, Shopping, Expense, Context-Link, Identity, Notification, or permission model without an explicit architectural decision.
6. If another active worker overlaps, **comment before coding** and agree on a split, dependency, shared contract, or handoff. Silent duplicate implementation is prohibited.

## Claim protocol

When active implementation begins:

- add the existing `in progress` label to the work issue;
- add one structured claim comment to the issue;
- keep that comment current when scope, touched contracts, or dependencies change;
- link the branch/PR as soon as it exists.

Use this format:

```md
<!-- coordination:claim:v1 -->
## Work claim
- Worker: @<login> (agent|human)
- Scope: <precise deliverable>
- Touches: <domains, APIs, migrations, UI surfaces, likely paths>
- Coordination keys: domain:<name>, model:<name>, api:<stable-contract>, ui:<surface>, migration:<app-or-table>
- Contracts changed: <none or explicit contracts>
- Depends on: #...
- Parallel-safe with: #...
- Avoids / out of scope: ...
- Branch/PR: <branch or #PR>
- Collision scan: #223 + open `in progress` issues + open PRs checked
```

### Coordination keys

`Coordination keys` are short, machine-readable collision identifiers. Add only keys that this work can materially change. Reuse the same spelling when the same contract is involved.

Recommended namespaces:

- `domain:<canonical-domain>` — e.g. `domain:calendar`, `domain:documents`
- `model:<stable-model-or-aggregate>` — e.g. `model:FamilyEvent`
- `api:<contract>` — e.g. `api:calendar-events`, `api:auth-session`
- `ui:<surface>` — e.g. `ui:calendar-hub`, `ui:today`
- `migration:<area>` — e.g. `migration:family`, `migration:documents`
- `worker:<queue-or-processor>` — e.g. `worker:document-processing`
- `policy:<cross-cutting-policy>` — e.g. `policy:permissions`, `policy:entitlements`

Do not use broad keys such as `domain:backend` or `ui:frontend`. The dashboard in #223 flags identical active keys even when the PRs do not yet touch the same files.

A claim is a coordination reservation, not ownership of a whole domain. Keep scope narrow enough that another worker can safely take adjacent work.

### Collision rule

If two claims overlap materially, do not race. Prefer, in order:

1. split by independent interface or layer;
2. make one worker publish the shared contract first;
3. rebase one workstream onto the other;
4. explicitly hand off one scope.

Whenever a change affects another active issue's contract, comment on that issue/PR immediately. Do not wait until review.

## Handoff / pause / finish

Use comments so another contributor can resume without reconstructing hidden context.

```md
<!-- coordination:handoff:v1 -->
## Handoff
- Completed: ...
- Remaining: ...
- Decisions / invariants: ...
- Tests run: ...
- Risks / open questions: ...
- Suggested next files/issues: ...
```

When work is paused or abandoned, remove `in progress` and explain why. When work is complete, only remove `in progress` after the acceptance criteria and merge/defined completion state are satisfied.

## Human-first collaboration

Humans and agents use the same visible protocol. Agents must not monopolize broad areas with vague claims. If a human contributor is already working the same scope, coordinate in comments and yield/split rather than duplicating their work.

External contributors are **not** required to perform market research for us. Maintainers/agents enrich external product-feature issues before implementation using the research protocol below.

## Mandatory research for external product-feature issues

Before an external product-feature issue may be merged, a maintainer/agent must add a current research comment containing the marker `<!-- external-research:v1 -->`.

The research must use fresh web sources and compare **3–5 relevant competitors**, prioritizing current category leaders/high-rated products where credible evidence exists. Prefer primary product/help/docs sources; use app-store/review evidence only to understand adoption or UX patterns, not as proof of technical quality.

Required block:

```md
<!-- external-research:v1 -->
## External issue research
### Problem and existing FamilyOS fit
- User problem: ...
- Existing FamilyOS capability/core: ...
- Roadmap fit / gate in #223: ...

### Current competitor evidence
| Product | Current pattern | Evidence/source | What works | Trade-off / risk |
|---|---|---|---|---|
| ... | ... | https://... | ... | ... |

### Cross-competitor synthesis
- Repeated successful pattern: ...
- Accessibility/mobile/privacy observations: ...
- What FamilyOS should deliberately not copy: ...

### FamilyOS decision
- Decision: adopt | adapt | reject | defer
- Proposed scope: ...
- Reused canonical cores/adapters: ...
- Security/permission implications: ...
- Migration/rollback implications: ...
- Acceptance criteria changes: ...
- Research date: YYYY-MM-DD
```

Refresh research if the market-sensitive evidence is stale or the issue materially changed.

## Pull requests

Every non-trivial PR should reference its work issue and use `.github/PULL_REQUEST_TEMPLATE.md`.

Before requesting merge:

- confirm the claim/handshake is visible on the issue;
- re-check open overlapping PRs after your final rebase/update;
- document any intentional overlap;
- include tests, migration/rollback notes, permission regressions, and user docs required by #223;
- for external feature issues, link the required `external-research:v1` comment.

The automated coordination dashboard in #223 is advisory but should be treated as the default shared situational picture. Semantic key/file-overlap warnings require an explicit handshake; they are not automatic proof that one PR is wrong.
