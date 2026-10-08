#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="${1:-$ROOT/caddy-local-root.crt}"
cd "$ROOT"
CID=$(docker compose ps -q caddy)
[[ -n "$CID" ]] || { echo "Caddy läuft nicht. Starte zuerst: docker compose up -d" >&2; exit 1; }
docker cp "$CID:/data/caddy/pki/authorities/local/root.crt" "$OUT"
chmod 644 "$OUT"
echo "Caddy Root-CA exportiert: $OUT"
echo "Installiere dieses Zertifikat ausschließlich auf Geräten, die deiner fam-uh-le Installation vertrauen sollen."
