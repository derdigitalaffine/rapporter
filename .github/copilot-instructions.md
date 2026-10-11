# FamilyOS repository instructions

Read and follow `../AGENTS.md` before planning or editing code. It is the shared coordination contract for humans and coding agents in this repository.

In particular:

- treat issue #223 as the central roadmap/architecture control issue;
- before coding, scan the target issue, open issues labeled `in progress`, and open pull requests for overlap;
- for non-trivial work, create or update exactly one canonical claim using the **exact** `<!-- coordination:claim:v2 -->` marker and fields from `AGENTS.md`;
- keep `Phase`, `Branch`, `PR`, `Coordination keys` and scope current; `discovery` may have no branch, but `implementation` must name one and `review` must name the PR;
- never create a second active claim for the same implementation branch/deliverable; choose one canonical delivery issue and hand off/supersede accidental duplicates before continuing;
- communicate material branch/key/file/contract overlap through GitHub comments before changing the same contract/scope in parallel;
- prefer narrow scopes, explicit merge order, and resumable handoffs over broad ownership;
- when a handoff is `superseded`, `paused`, or `abandoned`, remove `in progress` from the non-active issue so it stops reserving scope;
- use standalone `Closes/Fixes/Resolves #...` relationship lines only when a PR really completes that issue; use `Refs` / `Part of` for partial work;
- reuse canonical FamilyOS domains/cores rather than creating parallel models;
- for external product-feature requests, do not ask the reporter to perform product research: a maintainer/agent must add the standardized `external-research:v1` competitor/web-research block before merge;
- keep plans, decisions, dependencies, and handoffs visible in GitHub so humans and other agents can resume the work without private context.

Also follow `CONTRIBUTING.md` and the relevant product/architecture documentation for the area being changed.
