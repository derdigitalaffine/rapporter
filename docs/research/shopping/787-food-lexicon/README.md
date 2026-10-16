# #787 – German food lexicon research package

This is an **optional, removable research package** for #783/#785. It provides a small conservative lexicon, positive/negative evaluation fixtures and a reproducible evaluator. It does not replace manual shopping categories and does not create health, allergen or aisle-position truth.

## Source/licence decision

| Source | Decision | Use in this package | Licence conclusion |
| --- | --- | --- | --- |
| Project-authored rules/fixtures | **adopt** | All 15 bundled entries and all eval cases | Newly authored in this repository; no external corpus text copied |
| Open Food Facts taxonomies | **defer-copy** | Architecture/research reference only (DAG, translations, synonyms) | The server repository is AGPL software, but that alone does **not** establish the redistribution licence of taxonomy data. Copying taxonomy content stays blocked until the data licence is explicitly verified. |

This deliberately follows the issue requirement to distinguish a data licence from a software licence instead of guessing.

## Data model

`lexicon.json` separates:

- stable semantic `id`
- German display label and aliases
- semantic parent
- broad shopping department
- explicit negative examples/ambiguity notes
- provenance

Taxonomy and shopping department are different axes. Examples encoded in the sample:

- `H-Milch` and `Frischmilch` have different department mappings.
- `Hafermilch` maps to plant drink, not dairy.
- fresh tomatoes and canned tomatoes are distinct.
- fresh and frozen herbs are distinct.
- bare `Basilikum`/`Kräuter` intentionally abstain because preparation state is unknown.
- household and pet items can be recognized without pretending they are foods.

There are no store-specific aisle numbers and no health/allergen classifications.

## Matching policy

`evaluate.py` is intentionally conservative:

1. Unicode/case/hyphen variants are normalized.
2. Only explicit phrase aliases are matched; fuzzy typo correction is disabled.
3. A generic alias fully contained inside a more specific alias is suppressed (`Milch` inside `H-Milch`, `Tomaten` inside `gehackte Tomaten`).
4. If distinct concepts remain, the result is `ABSTAIN`.
5. Unknown input remains `ABSTAIN` and therefore remains manually creatable.

This is a testable baseline, not a production NLP model.

## Evaluation

The evaluation set is stored separately from the lexicon definitions. Positive inputs add context, quantities, spelling variants or composition. Negative cases cover root collisions, unknown terms, typos and deliberate ambiguity.

Run:

```bash
python3 docs/research/shopping/787-food-lexicon/validate.py
```

The current 23-case fixture produces deterministic metrics from the evaluator rather than a hand-written accuracy claim. With this exact sample it passes all expected cases; the important policy is that metrics are recomputed whenever entries or fixtures change.

The evaluator reports precision, recall, abstention and accuracy overall and per fixture group. A larger follow-up dataset must keep rule-authoring/training cases separate from held-out evaluation cases.

## Review workflow for additions

For every new entry:

1. choose a stable semantic ID; never recycle an old ID for a different concept;
2. record provenance and licence status;
3. add positive context cases that are not simple copies of the alias list;
4. add negative/root-collision and ambiguity cases;
5. check whether the term means food taxonomy, shopping department or a store-specific placement – do not collapse those axes;
6. run `validate.py`;
7. manually review a sample of changed predictions;
8. publish family-specific corrections only through an explicit separate process – never promote them globally by default.

## Removal/rollback

The package is safe to disable: unknown or previously manual items remain valid shopping-list text. Consumers must treat reference matches as optional hints. Package removal must not delete user categories or private family corrections.
