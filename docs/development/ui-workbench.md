# UI Workbench

Refs #754, #753; architecture and delivery order: #223.

## Development

From `frontend`, use `npm ci`, `npm run storybook` (port 6006), or
`npm run build-storybook`. The workbench is a dev-only Vite entry point. It
imports the production Nunito font, translations, CSS and components in the
application order, not a second theme. No application boot, PWA managers,
telemetry or service worker is loaded. Only brand assets are copied.

Fixtures are synthetic and deterministic. The preview intercepts the synthetic
session request; any unconfigured API call is rejected, never sent to a server.
Do not introduce real sessions, customer data, analytics or production URLs.
Local storage is not an alternative fixture database.

## Gates

`npm run ui:boundaries` and `node --test tests/ui-boundaries.test.mjs` run without
a browser and enforce production/workbench and headless-wrapper boundaries.
`npm run build` must remain independent of Storybook code.

Per #223, do not install or run local Chromium. `ui-workbench.yml` executes the
official Storybook Vitest browser integration and addon-a11y with
`a11y.test: error` in GitHub Actions. There is no global axe exclusion. The
additional Playwright suite covers 320/390/1024/1440px, reduced motion, overflow,
absence of API traffic/service workers and screenshots. It does not replace
existing application E2E/domain tests.

Production FormShell/Section/Field/Row/Choice/Actions, ErrorSummary and
EntityPicker have stories for long German strings, amounts, empty, disabled,
loading, error, offline-stale and unavailable states. Feedback stories exercise
the real promise confirmation, toast action/close and ListEditor quick sheet.
Interactions assert focus restoration, error-link focus, selection/removal and
the primary sheet action becoming enabled. New #753 primitives extend these
stories rather than creating duplicate controls.

## Review

Inspect CI interaction results, axe failures and attached viewport screenshots.
Review production token fidelity, keyboard order, labels, focus restoration,
reduced motion and long content. Browser emulation is not physical iOS/Android
software-keyboard, native zoom or screen-reader acceptance: record those
separately before claiming #753 parity. Do not infer physical evidence from
green CI. Never globally suppress accessibility rules to pass the gate.

Rollback removes this isolated tooling/workflow only; production data,
permissions, routing and PWA caches are unchanged.
