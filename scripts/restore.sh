#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="$ROOT/.env"
DUMP="${1:-}"
YES="${2:-}"

usage(){ echo "Verwendung: bash scripts/restore.sh /pfad/backup.dump [--yes]"; }
[[ -n "$DUMP" ]] || { usage; exit 2; }
[[ -f "$DUMP" ]] || { echo "Fehler: Backup nicht gefunden: $DUMP" >&2; exit 1; }
[[ -f "$ENV_FILE" ]] || { echo "Fehler: $ENV_FILE fehlt." >&2; exit 1; }

read_env(){ local key="$1"; grep -E "^${key}=" "$ENV_FILE" | tail -n1 | cut -d= -f2-; }
POSTGRES_DB="$(read_env POSTGRES_DB)"; POSTGRES_DB="${POSTGRES_DB:-famuhle}"
POSTGRES_USER="$(read_env POSTGRES_USER)"; POSTGRES_USER="${POSTGRES_USER:-famuhle}"

if [[ "$YES" != "--yes" ]]; then
  echo "ACHTUNG: Die aktuelle fam-uh-le-Datenbank '$POSTGRES_DB' wird durch '$DUMP' ersetzt."
  read -r -p "Zum Fortfahren exakt RESTORE eingeben: " answer
  [[ "$answer" == "RESTORE" ]] || { echo "Abgebrochen."; exit 1; }
fi

cd "$ROOT"
docker compose up -d db

echo "Stoppe App-Dienste …"
docker compose stop backend scheduler caddy >/dev/null 2>&1 || true

cleanup(){ docker compose up -d backend scheduler caddy >/dev/null 2>&1 || true; }
trap cleanup EXIT

echo "Stelle Datenbank wieder her …"
docker compose exec -T db dropdb --if-exists -U "$POSTGRES_USER" "$POSTGRES_DB"
docker compose exec -T db createdb -U "$POSTGRES_USER" "$POSTGRES_DB"
cat "$DUMP" | docker compose exec -T db pg_restore --no-owner --no-acl -U "$POSTGRES_USER" -d "$POSTGRES_DB"

echo "Starte fam-uh-le …"
docker compose up -d backend scheduler caddy
trap - EXIT

echo "Restore abgeschlossen. Status:"
docker compose ps
