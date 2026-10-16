#!/usr/bin/env python3
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

BASE = Path(__file__).resolve().parent
VALID_GTIN_LENGTHS = {8, 12, 13, 14}
PRODUCT_COLUMNS = {
    "gtin",
    "product_name",
    "brand",
    "quantity",
    "source_category",
    "mapped_category_id",
    "source_namespace",
    "source_id",
    "source_revision",
    "countries_evidence",
    "verified_at",
    "confidence",
    "status",
}
EVAL_COLUMNS = {
    "case_id",
    "input_kind",
    "input",
    "expected_action",
    "expected_gtin",
    "notes",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def valid_gtin(value: str) -> bool:
    if not value.isdigit() or len(value) not in VALID_GTIN_LENGTHS:
        return False
    body = value[:-1]
    total = sum(
        int(digit) * (3 if index % 2 == 0 else 1)
        for index, digit in enumerate(reversed(body))
    )
    expected = (10 - (total % 10)) % 10
    return expected == int(value[-1])


def read_csv(path: Path) -> tuple[list[dict[str, str]], set[str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        return list(reader), set(reader.fieldnames or [])


def main() -> int:
    errors: list[str] = []
    manifest = json.loads((BASE / "manifest.json").read_text(encoding="utf-8"))
    products, product_columns = read_csv(BASE / "products.csv")
    eval_cases, eval_columns = read_csv(BASE / "eval-cases.csv")

    if product_columns != PRODUCT_COLUMNS:
        errors.append(
            f"products.csv columns mismatch: expected {sorted(PRODUCT_COLUMNS)}, got {sorted(product_columns)}"
        )
    if eval_columns != EVAL_COLUMNS:
        errors.append(
            f"eval-cases.csv columns mismatch: expected {sorted(EVAL_COLUMNS)}, got {sorted(eval_columns)}"
        )

    expected_products = manifest["scope"]["product_count"]
    expected_eval_cases = manifest["scope"]["eval_case_count"]
    if len(products) != expected_products:
        errors.append(f"product count mismatch: manifest={expected_products}, csv={len(products)}")
    if len(eval_cases) != expected_eval_cases:
        errors.append(f"eval count mismatch: manifest={expected_eval_cases}, csv={len(eval_cases)}")

    gtins: set[str] = set()
    for row_number, row in enumerate(products, start=2):
        gtin = row["gtin"]
        if gtin in gtins:
            errors.append(f"products.csv:{row_number}: duplicate GTIN {gtin}")
        gtins.add(gtin)
        if not valid_gtin(gtin):
            errors.append(f"products.csv:{row_number}: invalid GTIN/check digit {gtin}")
        if row["source_id"] != gtin:
            errors.append(f"products.csv:{row_number}: source_id must equal GTIN for this fixture")
        if row["status"] != "active":
            errors.append(f"products.csv:{row_number}: unsupported status {row['status']!r}")
        try:
            confidence = float(row["confidence"])
        except ValueError:
            errors.append(f"products.csv:{row_number}: confidence is not numeric")
        else:
            if not 0.0 <= confidence <= 1.0:
                errors.append(f"products.csv:{row_number}: confidence outside 0..1")
        if not row["source_revision"]:
            errors.append(f"products.csv:{row_number}: source_revision is required")

    seen_case_ids: set[str] = set()
    for row_number, row in enumerate(eval_cases, start=2):
        case_id = row["case_id"]
        if case_id in seen_case_ids:
            errors.append(f"eval-cases.csv:{row_number}: duplicate case_id {case_id}")
        seen_case_ids.add(case_id)

        kind = row["input_kind"]
        action = row["expected_action"]
        value = row["input"]
        expected_gtin = row["expected_gtin"]

        if kind == "barcode":
            is_valid = valid_gtin(value)
            if action == "MATCH":
                if not is_valid:
                    errors.append(f"eval-cases.csv:{row_number}: MATCH requires valid GTIN")
                if value not in gtins:
                    errors.append(f"eval-cases.csv:{row_number}: MATCH GTIN missing from products.csv")
                if expected_gtin != value:
                    errors.append(f"eval-cases.csv:{row_number}: MATCH expected_gtin must equal input")
            elif action == "REJECT_INVALID_GTIN":
                if is_valid:
                    errors.append(f"eval-cases.csv:{row_number}: reject fixture unexpectedly has valid GTIN")
                if expected_gtin:
                    errors.append(f"eval-cases.csv:{row_number}: invalid GTIN fixture must not bind a product")
            else:
                errors.append(f"eval-cases.csv:{row_number}: unsupported barcode action {action}")
        elif kind == "text":
            if action not in {"ABSTAIN", "GENERIC_ITEM"}:
                errors.append(f"eval-cases.csv:{row_number}: unsupported text action {action}")
            if expected_gtin:
                errors.append(f"eval-cases.csv:{row_number}: text fixture must not force a GTIN")
        elif kind == "source_event":
            if action != "TOMBSTONE_ONLY":
                errors.append(f"eval-cases.csv:{row_number}: source_event must be TOMBSTONE_ONLY")
            if not valid_gtin(value) or value not in gtins or expected_gtin != value:
                errors.append(f"eval-cases.csv:{row_number}: tombstone must reference an existing valid GTIN")
        else:
            errors.append(f"eval-cases.csv:{row_number}: unsupported input_kind {kind}")

    for entry in manifest["files"]:
        path = BASE / entry["path"]
        if not path.is_file():
            errors.append(f"manifest file missing: {entry['path']}")
            continue
        actual = sha256(path)
        if actual != entry["sha256"]:
            errors.append(
                f"checksum mismatch for {entry['path']}: manifest={entry['sha256']} actual={actual}"
            )

    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1

    print(
        "OK: "
        f"{len(products)} products, {len(eval_cases)} eval cases, "
        f"{sum(1 for row in products if row['countries_evidence'] == 'DE')} DE-evidence row(s); "
        "coverage claim remains none"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
