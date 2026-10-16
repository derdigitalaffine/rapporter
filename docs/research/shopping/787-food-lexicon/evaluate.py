#!/usr/bin/env python3
"""Conservative, reproducible evaluator for the optional #787 lexicon sample."""
from __future__ import annotations

import csv
import json
import re
import unicodedata
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ABSTAIN = "ABSTAIN"


def fold(text: str) -> str:
    text = text.casefold().replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"[-_/]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def phrase_spans(text: str, phrase: str):
    text, phrase = fold(text), fold(phrase)
    return [m.span() for m in re.finditer(r"(?<!\w)" + re.escape(phrase) + r"(?!\w)", text)]


lexicon = json.loads((ROOT / "lexicon.json").read_text(encoding="utf-8"))
entries = lexicon["entries"]


def classify(text: str) -> str:
    raw_matches = []
    for entry in entries:
        for alias in entry["aliases"]:
            for start, end in phrase_spans(text, alias):
                raw_matches.append({"id": entry["id"], "start": start, "end": end, "length": end - start})

    # Suppress a generic alias only when it is fully contained in a more specific
    # alias at the same text location. Separate concepts elsewhere still cause abstention.
    matches = []
    for candidate in raw_matches:
        contained = any(
            other["id"] != candidate["id"]
            and other["start"] <= candidate["start"]
            and other["end"] >= candidate["end"]
            and other["length"] > candidate["length"]
            for other in raw_matches
        )
        if not contained:
            matches.append(candidate["id"])
    ids = set(matches)
    return next(iter(ids)) if len(ids) == 1 else ABSTAIN


def load_cases(name: str):
    with (ROOT / name).open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


cases = load_cases("eval-positive.csv") + load_cases("eval-negative.csv")
groups = defaultdict(lambda: {"total": 0, "correct": 0, "expected_positive": 0, "predicted_positive": 0, "true_positive": 0, "abstained": 0})
failures = []

for case in cases:
    prediction = classify(case["input"])
    expected = case["expected_id"]
    bucket = groups[case["group"]]
    for target in (groups["ALL"], bucket):
        target["total"] += 1
        target["correct"] += int(prediction == expected)
        target["expected_positive"] += int(expected != ABSTAIN)
        target["predicted_positive"] += int(prediction != ABSTAIN)
        target["true_positive"] += int(prediction == expected and expected != ABSTAIN)
        target["abstained"] += int(prediction == ABSTAIN)
    if prediction != expected:
        failures.append((case["case_id"], case["input"], expected, prediction))


def metrics(bucket):
    precision = bucket["true_positive"] / bucket["predicted_positive"] if bucket["predicted_positive"] else 1.0
    recall = bucket["true_positive"] / bucket["expected_positive"] if bucket["expected_positive"] else 1.0
    abstention = bucket["abstained"] / bucket["total"] if bucket["total"] else 0.0
    accuracy = bucket["correct"] / bucket["total"] if bucket["total"] else 1.0
    return precision, recall, abstention, accuracy


for name in sorted(groups, key=lambda value: (value != "ALL", value)):
    p, r, a, acc = metrics(groups[name])
    print(f"{name}: precision={p:.3f} recall={r:.3f} abstention={a:.3f} accuracy={acc:.3f} n={groups[name]['total']}")

if failures:
    for case_id, text, expected, prediction in failures:
        print(f"FAIL {case_id}: {text!r}: expected={expected} got={prediction}")
    raise SystemExit(1)
