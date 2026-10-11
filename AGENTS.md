# FamilyOS Agent Coordination Contract

This repository is developed by humans and multiple fast, parallel coding agents. GitHub is the coordination plane. Do not create a second private planning system that other contributors cannot see.

## Authority order

1. **#223** is the central roadmap/control issue for cross-cutting priorities, gates, and architecture conflicts.
2. The **work issue** owns scope, acceptance criteria, the active claim, and handoffs.
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
6. If another active worker overlaps, **comment before coding** and agree on a split, dependency, shared contract, merge order, or handoff. Silent duplicate implementation is prohibited.

The pre-flight is a point-in-time check, not permanent permission. Re-run it when scope expands, before opening a PR, and after a meaningful rebase onto a busy `main`.

## Claim protocol

When non-trivial work becomes active, add the existing `in progress` label and one structured claim comment. **Use the exact HTML marker.** Plain text such as `coordination:claim:v2` is human-readable but intentionally treated as malformed by automation.

New claims use v2:

```md
<!-- coordination:claim:v2 -->
## Work claim
- Worker: @<login> (agent|human|agent-assisted)
- Phase: discovery | implementation | review | blocked
- Scope: <one bounded deliverable>
- Branch: <branch name or `none` during discovery>
- PR: <#number or `none` until opened>
- Touches: <domains, APIs, migrations, UI surfaces, likely paths>
- Coordination keys: <comma-separated keys, or `none`>
- Contracts changed: <none or explicit contracts>
- Depends on: #... | none
- Parallel-safe with: #... | <explicit adjacent scope> | none known
- Avoids / out of scope: ...
- Collision scan: #223 + open `in progress` issues + open PRs checked
```

### Claim invariants

- **One implementation branch has one canonical delivery issue.** Do not create a second active claim for the same branch/same deliverable. If an accidental duplicate appears, choose the canonical issue immediately and hand off/supersede the duplicate before further coding.
- `Phase: discovery` may legitimately have `Branch: none` and no PR. Keep discovery short and convert to `implementation` when code starts.
- `Phase: implementation` requires a branch. Link the PR as soon as it exists.
- `Phase: review` requires a PR and means implementation scope is frozen except for review/CI fixes.
- `Phase: blocked` must state the blocker in the issue. Do not quietly occupy a broad area while blocked.
- Update the existing canonical claim when phase, branch, contracts, keys, or material scope change. Do not stack competing active claims on the same issue.

Existing exact `<!-- coordination:claim:v1 -->` claims remain valid while work is in flight. Bare/approximate v1/v2 markers are legacy input: agents should repair them when they next touch the issue instead of creating another claim.

### Coordination keys

`Coordination keys` are short, machine-readable collision identifiers. Add only keys that this work can materially change. Reuse the same spelling when the same contract is involved. If no shared contract can plausibly collide, write `none` explicitly; omission is not equivalent to `none`.

Recommended namespaces:

- `domain:<canonical-domain>` — e.g. `domain:calendar`, `domain:documents`
- `model:<stable-model-or-aggregate>` — e.g. `model:FamilyEvent`
- `api:<contract>` — e.g. `api:calendar-events`, `api:auth-session`
- `ui:<surface>` — e.g. `ui:calendar-hub`, `ui:today`
- `migration:<area>` — e.g. `migration:family`, `migration:documents`
- `worker:<queue-or-processor>` — e.g. `worker:document-processing`
- `policy:<cross-cutting-policy>` — e.g. `policy:permissions`, `policy:entitlements`
- `workflow:<automation>` — e.g. `workflow:coordination-dashboard`

Do not use broad keys such as `domain:backend` or `ui:frontend`. A claim is a coordination reservation, not ownership of a whole domain.

### Collision rule

Treat these as strong collision signals, in order of severity:

1. same active branch or same canonical delivery issue;
2. identical coordination key for a contract either worker may change;
3. exact changed-file overlap between open PRs;
4. likely path overlap declared by active claims;
5. dependency or architecture overlap discovered during implementation.

If two claims overlap materially, do not race. Prefer, in order:

1. split by independent interface or layer;
2. make one worker publish the shared contract first;
3. sequence merge/rebase explicitly;
4. hand off/supersede one scope.

Whenever a change affects another active issue's contract, comment on that issue/PR immediately. Do not wait until review.

## Handoff / pause / finish

Use comments so another contributor can resume without reconstructing hidden context. New handoffs use v2:

```md
<!-- coordination:handoff:v2 -->
## Handoff
- Disposition: continue | superseded | paused | abandoned | completed
- Successor: #... | @... | none
- Branch/PR: <branch and/or #PR>
- Completed: ...
- Remaining: ...
- Decisions / invariants: ...
- Tests run: ...
- Risks / open questions: ...
- Suggested next files/issues: ...
```

Cleanup is part of the handoff:

- `continue`: keep `in progress`; another worker is explicitly continuing the same canonical issue.
- `superseded`, `paused`, or `abandoned`: remove `in progress` from the non-active issue immediately after posting the handoff.
- `completed`: remove `in progress` only after acceptance criteria and merge/defined completion state are satisfied.

A handoff that says work is no longer active while leaving the issue `in progress` creates a false reservation and should be fixed.

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

Use closing keywords only as a **declarative standalone relationship line** when the PR really completes the issue, for example `Closes #123`. Partial slices use `Refs #123` or `Part of #123`. Avoid prose such as “does not close #123” when a simple `Refs` line plus a Remaining section is clearer.

Before requesting merge:

- confirm the canonical claim/handshake is visible on the issue;
- move the claim to `Phase: review` and ensure Branch/PR are current;
- re-check open overlapping claims/PRs after the final rebase/update;
- document any intentional overlap and merge order;
- include tests, migration/rollback notes, permission regressions, and user docs required by #223;
- for external feature issues, link the required `external-research:v1` comment.

The automated coordination dashboard in #223 is advisory but should be treated as the default shared situational picture. Branch, semantic-key, malformed-claim, file-overlap, stale-claim, and handoff-cleanup warnings require judgment and usually an explicit repair/handshake; they are not automatic proof that one PR is wrong.
