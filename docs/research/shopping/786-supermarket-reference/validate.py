#!/usr/bin/env python3
"""Validate the optional #786 supermarket reference research package."""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REQUIRED_CHAIN = {"chain_id", "canonical_name", "country_region", "source_status"}
REQUIRED_SAMPLE = {"sample_id", "chain_id", "source_namespace", "source_id", "verified_at", "confidence", "status"}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_csv(name: str):
    with (ROOT / name).open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def fail(message: str):
    raise SystemExit(f"ERROR: {message}")


manifest = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
if manifest.get("optional") is not True:
    fail("package must remain optional")
if manifest.get("coverage", {}).get("completeness_claim") is not False:
    fail("package must not claim Germany completeness")
if manifest.get("privacy", {}).get("contains_private_household_data") is not False:
    fail("private household data is forbidden")

chains = read_csv("chains.csv")
samples = read_csv("sampling.csv")
if len(chains) != 7 or len(samples) != 2:
    fail("deterministic sample counts changed; update manifest and review scope")

chain_ids = [row["chain_id"] for row in chains]
if len(chain_ids) != len(set(chain_ids)):
    fail("duplicate chain_id")
for row in chains:
    if not REQUIRED_CHAIN.issubset(row) or any(not row[key].strip() for key in REQUIRED_CHAIN):
        fail(f"incomplete chain row: {row}")
if "de.netto-salling" not in chain_ids or "de.netto-marken-discount" not in chain_ids:
    fail("the two unrelated Netto chains must stay distinct")

sample_ids = set()
for row in samples:
    if not REQUIRED_SAMPLE.issubset(row) or any(not row[key].strip() for key in REQUIRED_SAMPLE):
        fail(f"incomplete sample row: {row}")
    if row["sample_id"] in sample_ids:
        fail(f"duplicate sample_id: {row['sample_id']}")
    sample_ids.add(row["sample_id"])
    if row["chain_id"] not in chain_ids:
        fail(f"unknown chain reference: {row['chain_id']}")
    lat, lon = float(row["latitude"]), float(row["longitude"])
    confidence = float(row["confidence"])
    if not (-90 <= lat <= 90 and -180 <= lon <= 180 and 0 <= confidence <= 1):
        fail(f"invalid coordinates/confidence: {row['sample_id']}")
    if row["status"] != "evidence_only":
        fail("samples without element-level verification must remain evidence_only")

for entry in manifest["files"]:
    path = ROOT / entry["path"]
    if sha256(path) != entry["sha256"]:
        fail(f"checksum mismatch: {entry['path']}")
    actual = len(read_csv(entry["path"]))
    if actual != entry["records"]:
        fail(f"record count mismatch: {entry['path']}")

print("OK #786: 7 chains, 2 evidence-only real-world samples, 0 importable store records; no completeness claim.")
