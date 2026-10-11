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

## Historical reproducibility

New preventive appointment events copy the exact package ID, source key/version, checksum, rule key and age window into their private event payload. Existing events use `get_or_create` and are therefore not silently rewritten when a newer reference package is published. Appointment-question validation accepts stable exam keys from published and superseded history.

Until the first reviewed `de_pediatric_standard` package is published, the existing server-side U-exam schedule remains available as an explicitly marked `bundled_fallback`. This preserves current behavior without pretending the fallback is a reviewed/published database package. Vaccination rules are not fabricated in the fallback; they enter production only through the reviewed publish workflow.
