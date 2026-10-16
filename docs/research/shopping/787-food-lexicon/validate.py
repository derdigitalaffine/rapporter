#!/usr/bin/env python3
"""Structural/licence-boundary checks for #787."""
from __future__ import annotations

import csv
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def fail(msg: str):
    raise SystemExit(f"ERROR: {msg}")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


manifest = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
lexicon = json.loads((ROOT / "lexicon.json").read_text(encoding="utf-8"))
entries = lexicon["entries"]

ids = [e["id"] for e in entries]
if len(ids) != len(set(ids)):
    fail("duplicate stable id")
if len(entries) != 15:
    fail("sample count changed; review manifest and evaluation split")
if any(e.get("provenance") != "project-authored" for e in entries):
    fail("this sample must not silently copy unresolved external taxonomy content")
if any(not e.get("aliases") for e in entries):
    fail("every entry needs at least one alias")

alias_owner = {}
for entry in entries:
    for alias in entry["aliases"]:
        key = alias.casefold()
        if key in alias_owner and alias_owner[key] != entry["id"]:
            fail(f"ambiguous alias {alias!r} shared by {alias_owner[key]} and {entry['id']}")
        alias_owner[key] = entry["id"]

for source in manifest["sources"]:
    if source["namespace"] == "openfoodfacts-taxonomy" and source["decision"] != "defer-copy":
        fail("OFF taxonomy copying must stay deferred until the data licence is explicitly established")

for spec in manifest["files"]:
    path = ROOT / spec["path"]
    if sha(path) != spec["sha256"]:
        fail(f"checksum mismatch: {spec['path']}")
    if spec["path"].endswith(".csv"):
        with path.open(encoding="utf-8", newline="") as handle:
            count = sum(1 for _ in csv.DictReader(handle))
        if count != spec["records"]:
            fail(f"count mismatch: {spec['path']}")

result = subprocess.run([sys.executable, str(ROOT / "evaluate.py")], cwd=ROOT)
if result.returncode:
    fail("evaluation failed")
print("OK #787: structure, provenance boundary, checksums and positive/negative evaluation passed.")
