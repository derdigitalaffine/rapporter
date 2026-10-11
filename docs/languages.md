# App languages

FamilyOS supports these selectable interface languages:

- Deutsch (`de`)
- English (`en`)
- Français (`fr`)
- Nederlands (`nl`)
- ไทย (`th`)

The selected language is stored locally in the browser under `famuhle-language` and is restored on the next visit.

Locale-sensitive formatting uses `de-DE`, `en-GB`, `fr-FR`, `nl-NL`, and `th-TH` respectively. Product names, protocol names, barcode symbologies, API identifiers, and other technical identifiers are intentionally kept unchanged where translating them would make them inaccurate.

## Translation maintenance

The original German and English resources remain in the existing feature i18n modules. French, Dutch, and Thai are additive bundles under `frontend/src/i18n-extra/`, registered by `additional-language-i18n.js`. New-language resources fall back to English when a newly introduced key has not yet been translated, so users never receive a misleading German fallback in a non-German locale.

Run `npm run i18n:check` from `frontend/` after changing language resources. The guard verifies the supported language contract, locale mappings, bundle registration, and interpolation placeholders. The Playwright i18n regression test also covers language switching and persistence through Thai.
