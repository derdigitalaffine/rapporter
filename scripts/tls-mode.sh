#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="$ROOT/.env"
MODE="${1:-}"

[[ -f "$ENV_FILE" ]] || { echo "Keine .env gefunden. Bitte zuerst: bash scripts/setup.sh" >&2; exit 1; }

if [[ "$MODE" != "internal" && "$MODE" != "public" && "$MODE" != "proxy" ]]; then
  printf 'Betriebsmodus [internal/public/proxy]: '
  read -r MODE
fi
[[ "$MODE" == "internal" || "$MODE" == "public" || "$MODE" == "proxy" ]] || { echo "Ungültiger Modus: $MODE" >&2; exit 1; }

read_env(){ grep -E "^$1=" "$ENV_FILE" | tail -1 | cut -d= -f2- || true; }
valid_port(){ [[ "$1" =~ ^[0-9]+$ ]] && (( $1 >= 1 && $1 <= 65535 )); }
valid_bind(){ [[ "$1" == "0.0.0.0" || "$1" == "127.0.0.1" || "$1" =~ ^([0-9]{1,3}\.){3}[0-9]{1,3}$ ]]; }

CURRENT_MODE=$(read_env TLS_MODE)
DOMAIN=$(read_env DOMAIN)
HTTP_PORT=$(read_env HTTP_PORT); HTTP_PORT=${HTTP_PORT:-80}
HTTPS_PORT=$(read_env HTTPS_PORT); HTTPS_PORT=${HTTPS_PORT:-443}
HTTP_BIND=$(read_env HTTP_BIND); HTTP_BIND=${HTTP_BIND:-0.0.0.0}
HTTPS_BIND=$(read_env HTTPS_BIND); HTTPS_BIND=${HTTPS_BIND:-0.0.0.0}
PUBLIC_PORT=$(read_env PUBLIC_PORT); PUBLIC_PORT=${PUBLIC_PORT:-443}
PUBLIC_SCHEME=https

if [[ "$MODE" == "proxy" ]]; then
  printf 'Öffentliche Domain [%s]: ' "$DOMAIN"
  read -r NEW_DOMAIN
  DOMAIN="${NEW_DOMAIN:-$DOMAIN}"
  CADDYFILE=Caddyfile.proxy
  COMPOSE_FILE=docker-compose.yml

  DEFAULT_BIND="$HTTP_BIND"
  DEFAULT_HTTP_PORT="$HTTP_PORT"
  if [[ "$CURRENT_MODE" != "proxy" ]]; then
    DEFAULT_BIND=127.0.0.1
    DEFAULT_HTTP_PORT=8080
    PUBLIC_PORT=443
  fi

  while :; do
    printf 'Interne HTTP-Bind-Adresse [%s]: ' "$DEFAULT_BIND"
    read -r NEW_BIND
    HTTP_BIND="${NEW_BIND:-$DEFAULT_BIND}"
    valid_bind "$HTTP_BIND" && break
    echo "Ungültige Bind-Adresse. Bitte IPv4-Adresse, 127.0.0.1 oder 0.0.0.0 verwenden."
  done
  while :; do
    printf 'Interner HTTP-Port für den Reverse Proxy [%s]: ' "$DEFAULT_HTTP_PORT"
    read -r NEW_HTTP_PORT
    HTTP_PORT="${NEW_HTTP_PORT:-$DEFAULT_HTTP_PORT}"
    valid_port "$HTTP_PORT" && break
    echo "Ungültiger Port. Erlaubt: 1–65535."
  done
  while :; do
    printf 'Öffentlicher HTTPS-Port [%s]: ' "$PUBLIC_PORT"
    read -r NEW_PUBLIC_PORT
    PUBLIC_PORT="${NEW_PUBLIC_PORT:-$PUBLIC_PORT}"
    valid_port "$PUBLIC_PORT" && break
    echo "Ungültiger Port. Erlaubt: 1–65535."
  done
else
  if [[ "$MODE" == "public" ]]; then
    printf 'Öffentliche Domain [%s]: ' "$DOMAIN"
    read -r NEW_DOMAIN
    DOMAIN="${NEW_DOMAIN:-$DOMAIN}"
    CADDYFILE=Caddyfile
  else
    printf 'Lokaler Hostname/IP [%s]: ' "$DOMAIN"
    read -r NEW_DOMAIN
    DOMAIN="${NEW_DOMAIN:-$DOMAIN}"
    CADDYFILE=Caddyfile.selfsigned
  fi
  COMPOSE_FILE='docker-compose.yml:docker-compose.override.yml'

  if [[ "$CURRENT_MODE" == "proxy" ]]; then
    HTTP_BIND=0.0.0.0
    HTTPS_BIND=0.0.0.0
    HTTP_PORT=80
    HTTPS_PORT=443
    echo "Wechsel aus proxy: Host-Ports werden auf 80/443 und Bind-Adressen auf 0.0.0.0 zurückgesetzt."
  fi
  PUBLIC_PORT="$HTTPS_PORT"
  if [[ "$MODE" == "public" && ( "$HTTP_PORT" != "80" || "$HTTPS_PORT" != "443" ) ]]; then
    echo "Hinweis: Let's Encrypt benötigt von außen normalerweise Port 80/443 oder passende Weiterleitungen durch einen vorgeschalteten Router."
  fi
fi

if [[ "$PUBLIC_PORT" == "443" ]]; then PUBLIC_HOST="$DOMAIN"; else PUBLIC_HOST="$DOMAIN:$PUBLIC_PORT"; fi
ORIGIN="$PUBLIC_SCHEME://$PUBLIC_HOST"
APP_URL="$ORIGIN"

python3 - "$ENV_FILE" "$MODE" "$COMPOSE_FILE" "$CADDYFILE" "$DOMAIN" "$PUBLIC_SCHEME" "$PUBLIC_HOST" "$PUBLIC_PORT" "$APP_URL" "$HTTP_BIND" "$HTTP_PORT" "$HTTPS_BIND" "$HTTPS_PORT" "$ORIGIN" <<'PY'
from pathlib import Path
import sys
p=Path(sys.argv[1])
(
    mode, compose_file, caddy, domain, public_scheme, public_host, public_port,
    app_url, http_bind, http_port, https_bind, https_port, origin,
)=sys.argv[2:]
lines=p.read_text().splitlines()
updates={
 'TLS_MODE':mode,
 'COMPOSE_FILE':compose_file,
 'CADDYFILE':caddy,
 'DOMAIN':domain,
 'PUBLIC_SCHEME':public_scheme,
 'PUBLIC_HOST':public_host,
 'PUBLIC_PORT':public_port,
 'APP_URL':app_url,
 'HTTP_BIND':http_bind,
 'HTTP_PORT':http_port,
 'HTTPS_BIND':https_bind,
 'HTTPS_PORT':https_port,
 'DJANGO_ALLOWED_HOSTS':f'{domain},backend,localhost,127.0.0.1',
 'CSRF_TRUSTED_ORIGINS':origin,
 'CORS_ALLOWED_ORIGINS':origin,
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
echo "Betriebsmodus auf '$MODE' gesetzt. App: $APP_URL"
if [[ "$MODE" == "proxy" ]]; then
  echo "Interner Upstream: http://$HTTP_BIND:$HTTP_PORT (kein veröffentlichter HTTPS-Port im fam-uh-le-Stack)"
fi
if [[ -n "$(docker compose ps -q backend 2>/dev/null || true)" ]]; then
  docker compose up -d --force-recreate caddy
  echo "Caddy wurde mit der neuen Port-/TLS-Konfiguration neu gestartet."
else
  echo "Der Stack läuft aktuell nicht. Beim nächsten 'docker compose up -d' wird der neue Modus verwendet."
fi
