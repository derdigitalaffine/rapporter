# Headless Interaction Primitives

Refs #753, #754, #223. FamilyOS tokens/CSS (#93), forms (#400) and product
experience (#578) remain authoritative. Base UI 1.9 supplies behavior only.

## Ownership and Imports

Only `src/ui/` may import `@base-ui/react/<primitive>`. Import canonical wrappers
from their files, not a library-wide barrel; `npm run ui:boundaries` enforces
this in production source. Domain validation, APIs, permissions and authorized
picker options stay with existing consumers. No domain or DB migration.

- `FamilyDialog`: global `confirmAction` adapter, cancellation-first focus,
  named/described alert dialog, explicit buttons, Escape cancellation, return
  focus. Outside press does not accept destructive requests. Concurrent promises
  queue rather than overwrite each other; host teardown cancels pending work.
- `FamilySheet`: ListEditor is the bounded real QuickCreateSheet consumer.
  Existing fields, primary/cancel/close controls and production sheet classes
  remain. Busy work prevents outside/Escape dismissal; no swipe-only controls.
- `FamilyCombobox`: PinComposer's existing server-filtered EntityPicker contract
  is the first real consumer. ID-based selection/removal, single/multiple,
  controlled async query, loading/empty/error and keyboard option navigation.
  The old EntityPicker remains for other consumers pending parity acceptance.
- `FamilyToast`: compatible `toast(message, options)` delegates timeout,
  pause-on-interaction/window blur, keyboard accessibility and announcement
  priority to the official manager. Error priority is assertive, other messages
  polite; Base UI provides its dedicated announcements rather than nested live
  regions. Identical active events update one toast; at most three visible.
  Action and close remain explicit; duration 0 means persistent.

New dialog/drawer popups carry `data-family-overlay-owner="base-ui"`. Their
insertion effect asks AccessibilityManager to release legacy background inert
attributes before Base UI layout effects establish modality. The legacy manager
still marks the global modal state for app chrome but does not label, focus,
trap, dismiss, or inert an owned popup. Unmigrated legacy overlays retain their
existing manager. Mixed/nested overlays need regression evidence before any
further consumer migration; do not delete the legacy manager yet.

## Keyboard and Viewport

`Drawer.VirtualKeyboardProvider` is scoped inside the real Drawer root and
measures its official Viewport. Only that sheet uses `--drawer-keyboard-inset`;
the legacy `--app-keyboard-inset` selectors exclude owned overlays, preventing
double application. `useAppViewport` still owns stable application chrome and
legacy sheets. Never translate/resize the permanent PWA navigation from a
VisualViewport scroll. The sheet action row stays reachable/sticky while its
content scrolls. Explicit Cancel/Close work without drag or swipe.

## Evidence and Rollout

The #754 workbench exercises production adapters plus headless picker states,
keyboard selection/removal, queued confirmations and toast deduplication. Browser
and axe evidence runs in GitHub Actions only, not local Chromium. Existing app
navigation/creation/Pinboard/offline E2E remain required.

Measured with Vite 8.3.4 and the same lockfile/toolchain: original production
entry 4,142.81 kB (gzip 1,221.30 kB); bounded POC entry 4,302.61 kB (gzip
1,276.86 kB). Cost +159.80 kB raw / +55.56 kB gzip, before #755 splitting.
No Storybook runtime is in production. Shared behavior is deliberately measured
instead of claiming headless is free.

Physical iOS/Android software keyboard, native screen readers and native 200%
zoom are NOT established by emulated CI. Record actual devices, versions and
outcomes on #753. Until those and visual/mobile parity are accepted, keep the
POC limited; no mass migration/removal of legacy code. This is an implementation
delivery, not a declaration that all issue acceptance criteria are complete.

Rollback each consumer to its prior wrapper/import and restore feedback adapter
and legacy CSS selectors; no domain data or server permission changes. Never
remove the ownership handshake while owned overlays remain mounted.
