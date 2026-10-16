# Lazy Feature Modules and Navigation

Refs #755 under #577; delivery order #223: #760 workbench, #761 bounded UI
POC, then this platform slice. Existing domains, APIs, ACLs, FamilyRuntime and
PWA update/cache ownership remain unchanged.

## Measured Baseline

Use `cd frontend && npm ci && npm run build:analyze`. The dev-only Vite plugin
builds the actual production graph in memory, writes ignored `bundle-report.json`
and reports entry plus its transitive static imports, not just the first file.
Each chunk includes raw/gzip bytes, import edges and module contributions. It
adds no runtime dependency or private data. Gzip uses Node zlib; Vite's printed
gzip estimator can differ slightly. Compare the analyzer with itself.

Measured 2026-10-16, Vite 8.3.4, same lockfile and production toolchain:

| Measurement | Before lazy migration (with #753) | After |
| --- | ---: | ---: |
| Initial JS, transitive raw | 4,302,547 bytes | 1,680,655 bytes |
| Initial JS, transitive gzip | 1,269,339 bytes | 497,691 bytes |
| Entry file, raw | 4,302,547 bytes | 1,313,522 bytes |

About 61% less initial JavaScript. Minor subsequent contract/documentation
changes may shift a few bytes; CI artifacts contain the authoritative graph.
Original main before #753 measured entry 4,142.81 kB / Vite gzip 1,221.30 kB.
The headless POC's cost is documented separately, not hidden in this reduction.

The previous initial graph included bwip-js renderer (~1.58 MB rendered module
contribution before minification), Markdown parser/editor and all rare hubs.
After splitting, NotesHub (~1.09 MB), barcode/LoyaltyCardEditor (~0.94 MB), maplibre
(~1.07 MB) and their specialist modules are non-initial. Most specialist hubs
now have named dynamic chunks. React, icons, translations, core Today/Todo/
Calendar/Shopping and their shared editors remain eager. Some shared GamesHub
and ExpenseEditor code remains in core task/capture paths: changing those
domain integrations is deliberately not bundled into a platform refactor.

`npm run bundle:check` enforces a documented 2 MB transitive initial JS ceiling
and verifies that measured heavy modules/rare hubs/Storybook do not leak into
the initial graph. This is a regression ceiling, not a target to fill. Existing
Superadmin build/output remains separate.

## Canonical Contracts

`feature-registry.js` is the one page truth: IDs, detail/family/query ownership,
optional `load: () => import('./Hub.jsx')` and existing UI capability gates.
`FeatureModule` derives adapters from that registry. App only binds its existing
hub props to those adapters; it has no separate loader switch/map. The eight
core routes stay eager. App's family/detail decisions now consume registry
metadata rather than duplicate lists. Query cleanup consumes the same metadata,
including expense selectors and contextual family IDs.

Known capability/module denials are checked before import. Unavailable
entitlement snapshots retain existing fail-open UI behavior; lazy import is
never server authorization. Statistics reuses its extracted lightweight access
state for existing guest/plan messages without loading report code. Disabled
care modules remain accessible to their legitimate setup managers. Domain
components/server still own final authorization and data loading.

The canonical #191 CreateFlowHost is deferred only when an action is present;
its existing renderer registry, callbacks, history and validation stay intact.
No second create dispatcher is introduced. Module loading has compact status,
unavailable/offline error, retry, existing SW update check and explicit reload
with the dirty-form/navigation guard. A failed specialist module never replaces
the entire shell. Family/content keys still unmount stale consumers; existing
loadRevision/family guards are unchanged.

## React Router Compatibility Spike

Experiment used isolated **react-router 8.4.0** (not a production dependency):

```sh
npm install --prefix /tmp/familyos-router-spike --no-save --package-lock=false react-router@8.4.0
node scripts/router-compatibility-spike.mjs /tmp/familyos-router-spike/node_modules/react-router/dist/production/index.js
```

The executable spike verifies all 30 existing query pages, special invite/
verify/reset path matches, same-URL create history state, back/forward and
registry-driven query cleanup. All query pages match the same `/` pathname
route: a router adapter must still use our registry/query resolver, guards,
special boot handling and overlay state. Memory-router compatibility does not
establish real PWA or browser behavior; those remain existing remote E2E gates.

Decision: **retain the existing lightweight Navigation Service**. Router
installation adds no route split benefit here: Vite's module imports and the
existing registry already provide it. A parallel location/state subscription
would expand migration risk for dirty forms and same-URL overlays. No router
runtime, loader/action framework or backend routing change is added. Reconsider
only when a concrete pathname/nesting requirement earns that migration.

## PWA, Validation and Rollback

Existing SW recursively caches referenced asset graphs at install, including
dynamic assets. Preserve this stronger installed-offline guarantee: route
splitting reduces initial evaluation/network on uncontrolled first load, but
does not claim reduced complete PWA install/cache size. SW release IDs,
activation, cache purge and dirty-safe update banner remain canonical. No second
cache/retry/update service is added. Failed imports have user retry/update/reload
paths without forced reload or private exception contents.

Local Node tests validate registry/query/family/unknown/capability contracts;
production build and bundle budget run locally. Per #223 there is no local
Chromium. `ui-platform.yml` runs real browser navigation/deep links, creation,
PWA chrome/update, entitlement/statistics and dedicated chunk failure/initial
request checks remotely. Existing CI is not replaced. Workbench still tests
shared controls. Physical device/AT evidence remains separate from emulation.

Rollback one `load` entry by restoring the corresponding eager App import;
keep registry metadata/query ownership. Or revert the platform slice as a whole.
No database, account, document, permission or SW migration needs reversing.
