# Multi-Agent Coordination in FamilyOS

FamilyOS assumes that several humans and coding agents may work at the same time. The coordination design therefore optimizes for **visible intent, narrow ownership, early collision detection, low-noise automation, and resumable handoffs**.

The central control issue is **#223**. It is not a task board replacement; it is the roadmap, architecture gate, and shared operational dashboard.

## 1. Sources of truth

| Layer | Source of truth | Purpose |
|---|---|---|
| Portfolio / architecture | #223 | priority, gates, cross-cutting decisions, automated status snapshot |
| Work item | individual issue | scope, acceptance criteria, canonical claim, handoffs, research |
| Implementation | pull request | code, tests, migration, review, merge state |
| Repository policy | `AGENTS.md`, `CONTRIBUTING.md` | shared human/agent rules |

Do not copy the same evolving plan into multiple places. Link instead.

## 2. Coordination lifecycle

### A. Discover

Before work starts, inspect:

- latest relevant decisions in #223;
- the target issue and comments;
- all open `in progress` issues;
- all open PRs touching the same domain or likely files;
- existing canonical cores/adapters.

This is the anti-duplication checkpoint. A short `Phase: discovery` claim may be created before a branch exists when the work needs contract/code archaeology. Discovery does not reserve a whole domain and should convert to implementation or be released quickly.

### B. Claim

New work uses one exact `<!-- coordination:claim:v2 -->` comment from `AGENTS.md`.

The claim describes a **bounded deliverable**, not a subsystem, and records:

- phase (`discovery`, `implementation`, `review`, `blocked`);
- canonical branch and PR state;
- likely touched surfaces/paths;
- explicit Coordination Keys or `none`;
- dependencies, parallel-safe neighbors, and non-goals.

A single implementation branch belongs to one canonical delivery issue. Two active claims for the same branch/deliverable are a coordination bug, even if both were created in good faith.

Good scope:

> Add restart-safe lease recovery to the transactional mail outbox and its tests; no template or account-flow changes.

Bad scope:

> Work on auth.

### C. Handshake

If another claim or PR overlaps, communicate in the most local shared place:

- same issue -> issue comment;
- dependent PR -> PR conversation;
- two different issues sharing a contract -> comment on both issues and link them;
- architecture/prioritization conflict -> #223.

State the split and sequencing explicitly. Example:

> I will own the server-side projection contract and migration. #321 can continue with UI against the documented response shape; I will not touch its React files. Merge server contract first, then rebase the UI slice.

### D. Implement

Move the claim to `Phase: implementation` and name the branch before changing code. Keep changes narrow. When a discovered requirement would materially expand the claim, update the issue claim first and re-run the collision scan.

A busy default branch changes the risk picture. Repeat the scan before opening the PR and after a significant rebase.

### E. Review

Move the claim to `Phase: review` when implementation scope is frozen and the PR is the active delivery artifact. Update the claim with the real PR number. Review/CI fixes may continue, but new feature scope should return to the issue before code expands.

### F. Handoff or finish

Use `<!-- coordination:handoff:v2 -->` with a disposition from `AGENTS.md`.

A handoff is incomplete until status cleanup matches the disposition:

- `continue`: keep `in progress`;
- `superseded`, `paused`, `abandoned`: remove `in progress` from the non-active issue;
- `completed`: remove it after the real Definition of Done is reached.

This matters because stale `in progress` labels create false reservations for every later worker.

## 3. What the first production usage taught us

The initial coordination system worked well enough to expose real failure modes quickly. The hardened contract deliberately addresses those observations rather than adding process for its own sake.

### Success: bounded parallel slices can work

The Superadmin #205 work demonstrated useful parallelism: multiple backend slices stayed independent, while the two PRs that both touched `backend/config/urls.py` documented an explicit merge/rebuild order. This is the intended model: parallelize independent contracts, serialize the shared seam.

### Failure mode: prose is not a reliable closing contract

Several PRs correctly used `Refs #205` and explicitly said they did **not** close the parent issue. The first dashboard parser nevertheless matched the words `close #205` inside that prose and produced false “multiple closing PRs” warnings.

Rule: closing relationships are parsed only from declarative standalone relationship lines such as `Closes #205`. Narrative prose is not a machine contract.

### Failure mode: visible but malformed claims

Some agents wrote `coordination:claim:v1` as plain text instead of the exact HTML marker. Humans could understand the intent, but automation classified the claim as missing. Hardened automation keeps these legacy/bare claims visible as malformed while new work must use the exact v2 marker.

### Failure mode: duplicate claim before PR overlap exists

#449/#450 showed that two agents can claim the same branch and same core files before PR-file overlap detection has anything to inspect. Branch identity therefore became a first-class collision signal. A duplicate branch claim should be resolved before more code is written.

### Failure mode: stale handoff reservations

A good handoff can still leave a bad global state if the superseded issue remains labeled `in progress`. Handoff disposition and label cleanup are now one operation from the coordination perspective.

### Failure mode: “no PR yet” can be legitimate

Discovery work should not be noisy merely because no PR exists. The dashboard now interprets phase: discovery without a PR is normal; implementation/review without a PR becomes attention-worthy only after a grace period.

## 4. Coordination Keys

Coordination Keys catch semantic collisions that file overlap alone misses: two agents can change the same API/model/policy contract in different files.

Examples:

- `domain:calendar`
- `model:FamilyEvent`
- `api:calendar-events`
- `ui:today`
- `worker:document-processing`
- `policy:permissions`
- `workflow:coordination-dashboard`

Use the same spelling for the same shared contract. Avoid broad keys such as `domain:backend`. Write `none` explicitly when a bounded slice really has no shared contract key; missing keys are treated as incomplete metadata, not as proof of safety.

## 5. Automated dashboard in #223

`.github/workflows/coordination-dashboard.yml` maintains one sticky comment in #223.

It shows:

- all open issues carrying `in progress`;
- claim quality (`v2`, legacy exact v1, malformed/bare, missing);
- phase, branch, Coordination Keys and linked open PRs;
- identical active branches;
- identical Coordination Keys;
- multiple PRs with real declarative closing lines for the same issue;
- exact changed-file overlap between open PRs;
- implementation/review claims that remain without a referencing PR after a grace period;
- stale-looking claims with no visible activity for 72 hours;
- handoffs whose disposition says work is inactive while `in progress` remains;
- open external feature requests still missing the mandatory research block.

The dashboard refreshes after issue/PR/comment state changes, manually, and on an hourly schedule.

### What warnings mean

Warnings request judgment or metadata repair, not automatic rejection:

- **same branch**: stop and choose one canonical delivery issue before further coding;
- **same Coordination Key**: verify shared-contract ownership/split;
- **same issue, several real closing PRs**: verify the issue is not being completed twice;
- **same file touched**: coordinate sequence or ownership before both PRs grow;
- **malformed claim**: repair the marker/fields instead of creating a duplicate claim;
- **implementation/review claim without PR**: link/open the PR or change phase/status if work is not actually at that stage;
- **handoff cleanup**: remove the stale reservation or correct the disposition;
- **research missing**: enrich the external feature issue before merge.

A partial PR should use `Refs #123` or `Part of #123`; only a standalone `Closes/Fixes/Resolves #123` line is treated as a closing relationship.

## 6. External issue research

External reporters should be able to describe a need without doing product-management work for the project. The maintainer/agent performing triage owns the research.

For product-feature requests from non-collaborators:

1. search the repository for existing/duplicate capabilities;
2. map the request to #223 and canonical cores;
3. research 3–5 current competitors on the web;
4. prioritize primary sources and current product behavior;
5. compare common successful patterns, privacy, accessibility, mobile flow, and trade-offs;
6. add the standardized `external-research:v1` comment;
7. only then convert the request into an implementation-ready scope.

The goal is not to clone competitors. The research answers: **what user expectation is established, which patterns work repeatedly, and what FamilyOS should intentionally do differently?**

## 7. Research quality bar

A useful competitor block includes evidence, not just names.

For each competitor capture:

- the exact workflow or behavior relevant to the issue;
- source URL and research date;
- whether the evidence is official documentation/product UI, store listing, or independent review;
- what reduces user effort;
- privacy/security/accessibility cost;
- whether the pattern fits FamilyOS's architecture and self-hosting goals.

Avoid:

- copying feature lists without testing relevance;
- relying on a single review site;
- treating star ratings as architecture evidence;
- importing cloud-only/AI-only behavior into a core workflow without fallback;
- creating a new FamilyOS domain just because a competitor models the feature separately.

## 8. Human contributor ergonomics

The process is designed to make external/human contribution easier:

- issue forms ask for the problem, not internal architecture knowledge;
- maintainers/agents do the roadmap and competitor enrichment;
- claims are soft reservations and can be split;
- claim phases distinguish exploration from implementation;
- PR templates make dependencies and overlap visible;
- no one needs access to an agent-only chat or private tracker to understand current work.

When an agent and a human collide, prefer a visible split or handoff. Agents must not silently recreate work already being done by a person.

## 9. Merge discipline

Before merging a non-trivial PR:

- linked canonical delivery issue is clear;
- claim is in `Phase: review` with current branch/PR;
- active handshakes and merge order are reflected in comments;
- no unresolved branch/semantic/file-overlap warning is ignored;
- tests and relevant CI are green;
- migration/rollback and negative permission tests satisfy #223 where applicable;
- user-facing docs are updated or linked;
- external feature research exists when required.

For a busy default branch, branch protection with required CI/review/conversation resolution is preferable to relying on convention alone. GitHub's merge queue is useful in eligible organization-owned repositories, but this repository should not assume availability of that feature.
