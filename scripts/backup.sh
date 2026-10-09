#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="$ROOT/.env"
BACKUP_DIR="${BACKUP_DIR:-$ROOT/backups}"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Fehler: $ENV_FILE fehlt. Zuerst Setup ausführen." >&2
  exit 1
fi

read_env(){ local key="$1"; grep -E "^${key}=" "$ENV_FILE" | tail -n1 | cut -d= -f2-; }
POSTGRES_DB="$(read_env POSTGRES_DB)"; POSTGRES_DB="${POSTGRES_DB:-famuhle}"
POSTGRES_USER="$(read_env POSTGRES_USER)"; POSTGRES_USER="${POSTGRES_USER:-famuhle}"

mkdir -p "$BACKUP_DIR"
chmod 700 "$BACKUP_DIR" 2>/dev/null || true
STAMP="$(date +%Y%m%d-%H%M%S)"
OUT="$BACKUP_DIR/famuhle-$STAMP.dump"
TMP="$OUT.tmp"

cd "$ROOT"
if ! docker compose ps --status running db >/dev/null 2>&1; then
  echo "Fehler: PostgreSQL-Container läuft nicht." >&2
  exit 1
fi

echo "Erstelle Datenbank-Backup …"
trap 'rm -f "$TMP"' EXIT
docker compose exec -T db pg_dump -Fc --no-owner --no-acl -U "$POSTGRES_USER" -d "$POSTGRES_DB" > "$TMP"
[[ -s "$TMP" ]] || { echo "Fehler: Backup ist leer." >&2; exit 1; }
mv "$TMP" "$OUT"
chmod 600 "$OUT"
trap - EXIT

printf 'Backup erstellt: %s\n' "$OUT"
ls -lh "$OUT"
