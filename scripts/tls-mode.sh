#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="$ROOT/.env"
MODE="${1:-}"

[[ -f "$ENV_FILE" ]] || { echo "Keine .env gefunden. Bitte zuerst: bash scripts/setup.sh" >&2; exit 1; }

if [[ "$MODE" != "internal" && "$MODE" != "public" ]]; then
  printf 'TLS-Modus [internal/public]: '
  read -r MODE
fi
[[ "$MODE" == "internal" || "$MODE" == "public" ]] || { echo "Ungültiger Modus: $MODE" >&2; exit 1; }

read_env(){ grep -E "^$1=" "$ENV_FILE" | tail -1 | cut -d= -f2- || true; }
DOMAIN=$(read_env DOMAIN)
if [[ "$MODE" == "public" ]]; then
  printf 'Öffentliche Domain [%s]: ' "$DOMAIN"
  read -r NEW_DOMAIN
  DOMAIN="${NEW_DOMAIN:-$DOMAIN}"
  CADDYFILE=Caddyfile
else
  printf 'Lokaler Hostname [%s]: ' "$DOMAIN"
  read -r NEW_DOMAIN
  DOMAIN="${NEW_DOMAIN:-$DOMAIN}"
  CADDYFILE=Caddyfile.selfsigned
fi

python3 - "$ENV_FILE" "$MODE" "$CADDYFILE" "$DOMAIN" <<'PY'
from pathlib import Path
import sys
p=Path(sys.argv[1]); mode,caddy,domain=sys.argv[2:]
lines=p.read_text().splitlines()
updates={
 'TLS_MODE':mode,
 'CADDYFILE':caddy,
 'DOMAIN':domain,
 'DJANGO_ALLOWED_HOSTS':f'{domain},backend,localhost,127.0.0.1',
 'CSRF_TRUSTED_ORIGINS':f'https://{domain}',
 'CORS_ALLOWED_ORIGINS':f'https://{domain}',
}
out=[]; seen=set()
for line in lines:
    if '=' in line and not line.lstrip().startswith('#'):
        key=line.split('=',1)[0]
        if key in updates:
            out.append(f'{key}={updates[key]}'); seen.add(key); continue
    out.append(line)
for k,v in updates.items():
    if k not in seen: out.append(f'{k}={v}')
p.write_text('\n'.join(out)+'\n')
PY

cd "$ROOT"
echo "TLS-Modus auf '$MODE' gesetzt. Host: $DOMAIN"
if docker compose ps >/dev/null 2>&1; then
  docker compose up -d --force-recreate caddy
  echo "Caddy wurde neu gestartet."
else
  echo "Beim nächsten 'docker compose up -d' wird der neue Modus verwendet."
fi
