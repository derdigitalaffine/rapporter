# Multi-Agent Coordination in FamilyOS

FamilyOS assumes that several humans and coding agents may work at the same time. The coordination design therefore optimizes for **visible intent, narrow ownership, early collision detection, and resumable handoffs**.

The central control issue is **#223**. It is not a task board replacement; it is the roadmap, architecture gate, and shared operational dashboard.

## 1. Sources of truth

| Layer | Source of truth | Purpose |
|---|---|---|
| Portfolio / architecture | #223 | priority, gates, cross-cutting decisions, automated status snapshot |
| Work item | individual issue | scope, acceptance criteria, claim, handoffs, research |
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

This is the anti-duplication checkpoint.

### B. Claim

Add `in progress` and a `coordination:claim:v1` comment. The claim describes a **bounded deliverable**, not a broad subsystem.

Good claim:

> Add restart-safe lease recovery to the transactional mail outbox and its tests; no template or account-flow changes.

Bad claim:

> Work on auth.

Each claim also carries narrow **Coordination Keys** such as `domain:calendar`, `model:FamilyEvent`, `api:calendar-events`, `ui:today`, `worker:document-processing` or `policy:permissions`. Keys are machine-readable collision identifiers for contracts that may be changed by the work. Use the same spelling for the same shared contract and avoid broad keys such as `domain:backend`.

This catches semantic collisions that file overlap alone misses: two agents can change the same API or model contract in different files.

### C. Handshake

If another claim or PR overlaps, communicate in the most local shared place:

- same issue -> issue comment;
- dependent PR -> PR conversation;
- two different issues sharing a contract -> comment on both issues and link them;
- architecture/prioritization conflict -> #223.

State the split explicitly. Example:

> I will own the server-side projection contract and migration. #321 can continue with UI against the documented response shape; I will not touch its React files.

### D. Implement

Keep changes narrow. When a discovered requirement would materially expand the claim, update the issue claim first and re-run the collision scan.

### E. Handoff or finish

A handoff comment should be enough for another contributor to continue without private context. Remove `in progress` only when intentionally paused/abandoned or after the issue's real Definition of Done is reached.

## 3. Automated dashboard in #223

`.github/workflows/coordination-dashboard.yml` maintains one sticky comment in #223.

It shows:

- all open issues carrying `in progress`;
- their latest structured claim and Coordination Keys;
- open PRs that reference the active issue via closing keywords, `Refs`, or `Part of`;
- active claims with identical Coordination Keys;
- PRs that simultaneously try to close the same issue;
- exact changed-file overlap between open PRs;
- active claims with no visible referencing PR yet;
- open external feature requests still missing the mandatory research block;
- stale-looking claims with no visible issue/linked-PR activity for 72 hours.

The dashboard refreshes after issue/PR/comment state changes, manually, and on an hourly schedule.

### What warnings mean

A warning is a request for human/agent judgment, not an automatic rejection:

- **same Coordination Key**: verify whether the shared contract has an explicit owner/split;
- **same issue, several closing PRs**: verify that scopes are intentionally split or ordered;
- **same file touched**: coordinate sequencing or ownership before both PRs grow;
- **claim without PR**: valid during exploration, but should not stay invisible for long;
- **research missing**: an external product-feature issue must be enriched before merge.

A partial PR can use `Refs #123` or `Part of #123` without falsely claiming that it closes the issue. The dashboard treats those as work links but reserves the “several PRs close the same issue” collision for actual closing keywords.

## 4. External issue research

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

## 5. Research quality bar

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

## 6. Human contributor ergonomics

The process is designed to make external/human contribution easier:

- issue forms ask for the problem, not internal architecture knowledge;
- maintainers/agents do the roadmap and competitor enrichment;
- claims are soft reservations and can be split;
- PR templates make dependencies and overlap visible;
- no one needs access to an agent-only chat or private tracker to understand current work.

When an agent and a human collide, prefer a visible split or handoff. Agents must not silently recreate work already being done by a person.

## 7. Merge discipline

Before merging a non-trivial PR:

- linked issue is clear;
- active claim and handshakes are reflected in comments;
- no unresolved semantic/file-overlap warning is ignored;
- tests and relevant CI are green;
- migration/rollback and negative permission tests satisfy #223 where applicable;
- user-facing docs are updated or linked;
- external feature research exists when required.

For a busy default branch, branch protection with required CI/review/conversation resolution is preferable to relying on convention alone. GitHub's merge queue is useful in eligible organization-owned repositories, but this repository should not assume availability of that feature.
