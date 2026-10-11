# Pediatric reference data

Pediatric preventive-care and vaccination rules are server-side, versioned reference packages. They are organizational reference data, not individualized medical advice.

## Lifecycle

A package is imported as `draft`, validated, explicitly published by a Django superuser, and later either superseded by a new version or reactivated as a rollback. Published and superseded package contents are immutable; rollback changes status rather than rewriting history.

The API surface is under `/api/baby/reference-packages/` (subject to the project's configured API prefix):

- `POST /baby/reference-packages/` — controlled draft import (superadmin)
- `PATCH /baby/reference-packages/{id}/` — edit a draft only (superadmin)
- `POST /baby/reference-packages/{id}/validate/` — schema/plausibility preview (superadmin)
- `POST /baby/reference-packages/{id}/publish/` — validate and publish, superseding the previous active version (superadmin)
- `POST /baby/reference-packages/{id}/supersede/` — explicitly retire the current version (superadmin)
- `POST /baby/reference-packages/{id}/reactivate/` — reactivate an immutable historical version (superadmin)
- `GET /baby/reference-packages/current/?source_key=...&locale=...&on=YYYY-MM-DD` — current effective published package
- `GET /baby/reference-packages/{id}/` — exact historical package by ID

Publish/supersede/reactivate actions are written to the central audit catalog with actor, package ID and stable source key. The audit metadata intentionally excludes medical payload content and free-text notes.

## Package metadata

Each package stores:

- `source_key`, `source_title`, `source_version`
- `published_at`, `effective_from`, `effective_to`, `imported_at`
- `status` (`draft`, `published`, `superseded`)
- `locale`
- SHA-256 `checksum` of canonical JSON payload
- `created_by`, `published_by`
- `reason`, `notes`
- optional `superseded_by` relation

A `(source_key, source_version, locale)` tuple is unique.

## Payload schema v1

```json
{
  "schema_version": 1,
  "u_exams": [
    {
      "key": "U6",
      "age_window": {
        "start_day": 304,
        "end_day": 365,
        "target_day": 335
      },
      "display": {
        "de": "U6",
        "window_label": "10.–12. Lebensmonat"
      },
      "source_url": "https://official.example/reference"
    }
  ],
  "vaccinations": [
    {
      "key": "stable_vaccine_group_key",
      "display": {"de": "Anzeigename"},
      "doses": [
        {
          "sequence": 1,
          "age_window": {"start_day": 42, "end_day": 84},
          "min_interval_days": 0
        },
        {
          "sequence": 2,
          "age_window": {"start_day": 84, "end_day": 140},
          "min_interval_days": 28
        }
      ],
      "boosters": [
        {"age_window": {"start_day": 330, "end_day": 450}}
      ]
    }
  ]
}
```

Validation rejects malformed/non-JSON payloads, duplicate stable keys, empty vaccination dose sequences, duplicate or non-increasing dose numbers, implausible negative/reversed age windows, target dates outside a window, and implausible minimum intervals.

## Historical reproducibility and calendar privacy

Family-wide calendar events remain deliberately generic: they contain no child identity, U-exam key, medical age window or pediatric source payload. Exact provenance is stored instead in the baby-scoped, immutable `PediatricPreventiveEventReference` relation linking the baby and generic event to the package ID, source key/version/checksum, stable rule key and exact age window.

New events bind that private record to the package version active when the event is first created. Existing events and their private provenance are not silently rewritten when a newer reference package is published. Legacy preventive events that predate the reference-package feature are bound to the explicit bundled fallback rather than retroactively attributed to a newer package. Appointment-question validation accepts stable exam keys from published and superseded history.

Until the first reviewed `de_pediatric_standard` package is published, the existing server-side U-exam schedule remains available as an explicitly marked `bundled_fallback`. This preserves current behavior without pretending the fallback is a reviewed/published database package. Vaccination rules are not fabricated in the fallback; they enter production only through the reviewed publish workflow.
