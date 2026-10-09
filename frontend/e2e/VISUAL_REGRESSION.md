# Visual regression baselines

The Playwright visual suite protects the main fam-uh-le surfaces at the two product breakpoints used in CI:

- mobile Chromium: 390×844
- desktop Chromium: 1440×900

Covered views are Today, Tasks, Shopping (planning and store mode), Calendar, Members, Integrations, Automations and More, plus the Task editor, Event editor and invitation-success dialogs.

## Run the gate

```bash
cd frontend
npm install
npm run build
npx playwright install --with-deps chromium
npm run e2e:visual
```

A pixel difference fails the Playwright job. CI always uploads `playwright-report` and `test-results`; on a visual failure it additionally uploads the actual/diff PNGs as a dedicated visual-regression artifact.

## Intentionally update baselines

Only update snapshots when the UI change is expected and reviewed. The committed baselines are produced on Linux with the same Chromium/Playwright setup as GitHub Actions, because font rasterization differs across operating systems.

On Linux:

```bash
cd frontend
npm install
npm run build
npx playwright install --with-deps chromium
npm run e2e:visual:update
```

Review every changed PNG under `e2e/visual-regression.spec.js-snapshots/` before committing it. Do not accept a baseline change only to make CI green; the screenshot diff is the review input.

The visual test freezes the browser clock and pins mocked task/event/integration timestamps, so snapshots must not be regenerated merely because the calendar date changed.
