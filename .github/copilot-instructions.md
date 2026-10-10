# FamilyOS repository instructions

Read and follow `../AGENTS.md` before planning or editing code. It is the shared coordination contract for humans and coding agents in this repository.

In particular:

- treat issue #223 as the central roadmap/architecture control issue;
- before coding, scan the target issue, open issues labeled `in progress`, and open pull requests for overlap;
- create/update the structured `coordination:claim:v1` issue comment when actively implementing non-trivial work;
- communicate material overlap through GitHub comments before changing the same contract/scope in parallel;
- prefer narrow scopes and explicit handoffs over broad ownership;
- reuse canonical FamilyOS domains/cores rather than creating parallel models;
- for external product-feature requests, do not ask the reporter to perform product research: a maintainer/agent must add the standardized `external-research:v1` competitor/web-research block before merge;
- keep plans, decisions, dependencies, and handoffs visible in GitHub so humans and other agents can resume the work without private context.

Also follow `CONTRIBUTING.md` and the relevant product/architecture documentation for the area being changed.
