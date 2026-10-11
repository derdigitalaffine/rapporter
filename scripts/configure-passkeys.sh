#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${ENV_FILE:-$ROOT_DIR/.env}"

fail() {
  echo "configure-passkeys: $*" >&2
  exit 1
}

env_value() {
  local key="$1" line
  line="$(grep "^${key}=" "$ENV_FILE" 2>/dev/null | tail -n1 || true)"
  printf '%s' "${line#*=}"
}

set_env() {
  local key="$1" value="$2" tmp
  [[ "$value" != *$'\n'* && "$value" != *$'\r'* ]] || fail "refusing newline in $key"
  tmp="$(mktemp)"
  grep -v "^${key}=" "$ENV_FILE" > "$tmp" || true
  printf '%s=%s\n' "$key" "$value" >> "$tmp"
  mv "$tmp" "$ENV_FILE"
}

[[ -f "$ENV_FILE" ]] || fail "missing $ENV_FILE; run ./scripts/setup.sh or copy .env.example first"

app_url="$(env_value APP_URL)"
if [[ -z "$app_url" ]]; then
  public_host="$(env_value PUBLIC_HOST)"
  public_scheme="$(env_value PUBLIC_SCHEME)"
  [[ -n "$public_host" ]] || fail "APP_URL and PUBLIC_HOST are both empty"
  app_url="${public_scheme:-https}://$public_host"
fi

while [[ "$app_url" == */ ]]; do app_url="${app_url%/}"; done
case "$app_url" in
  https://*) scheme=https ;;
  http://*) scheme=http ;;
  *) fail "APP_URL must start with https:// (or http://localhost for local development)" ;;
esac

authority="${app_url#*://}"
[[ -n "$authority" ]] || fail "APP_URL has no host"
[[ "$authority" != */* && "$authority" != *\?* && "$authority" != *\#* ]] || fail "APP_URL must be an origin without path, query or fragment"
[[ "$authority" != *@* ]] || fail "APP_URL must not contain userinfo"
[[ "$authority" != \[* ]] || fail "IPv6 literals are not supported as a WebAuthn RP ID; use a hostname"

host="$authority"
if [[ "$host" == *:* ]]; then
  port="${host##*:}"
  [[ "$port" =~ ^[0-9]+$ ]] || fail "APP_URL contains an invalid port"
  (( port >= 1 && port <= 65535 )) || fail "APP_URL port is outside 1-65535"
  host="${host%:*}"
fi

[[ -n "$host" ]] || fail "APP_URL has no hostname"
[[ "$host" != *'*'* ]] || fail "wildcard hosts are not valid WebAuthn RP IDs"
if [[ "$host" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  fail "WebAuthn needs a hostname, not an IPv4 address; configure FamilyOS with a DNS/mDNS hostname first"
fi
if [[ "$scheme" == http && "$host" != localhost ]]; then
  fail "WebAuthn requires HTTPS outside localhost; current APP_URL is $app_url"
fi

rp_id="$host"
existing_rp_id="$(env_value WEBAUTHN_RP_ID)"
if [[ -n "$existing_rp_id" && "$existing_rp_id" != familyos.local ]]; then
  if [[ "$host" == "$existing_rp_id" || "$host" == *".${existing_rp_id}" ]]; then
    rp_id="$existing_rp_id"
  fi
fi

rp_name="$(env_value WEBAUTHN_RP_NAME)"
rp_name="${rp_name:-FamilyOS}"
ttl="$(env_value WEBAUTHN_CHALLENGE_TTL_SECONDS)"
ttl="${ttl:-300}"
[[ "$ttl" =~ ^[1-9][0-9]*$ ]] || fail "WEBAUTHN_CHALLENGE_TTL_SECONDS must be a positive integer"

origin="$app_url"

if [[ "$(env_value WEBAUTHN_ENABLED)" == true \
  && "$(env_value WEBAUTHN_RP_ID)" == "$rp_id" \
  && "$(env_value WEBAUTHN_RP_NAME)" == "$rp_name" \
  && "$(env_value WEBAUTHN_ORIGIN)" == "$origin" \
  && "$(env_value WEBAUTHN_CHALLENGE_TTL_SECONDS)" == "$ttl" ]]; then
  chmod 600 "$ENV_FILE"
  echo "Passkeys are already configured for $origin (RP ID: $rp_id)."
  exit 0
fi

backup="$ENV_FILE.backup.passkeys.$(date +%Y%m%d-%H%M%S)"
cp -p "$ENV_FILE" "$backup"

set_env WEBAUTHN_ENABLED true
set_env WEBAUTHN_RP_ID "$rp_id"
set_env WEBAUTHN_RP_NAME "$rp_name"
set_env WEBAUTHN_ORIGIN "$origin"
set_env WEBAUTHN_CHALLENGE_TTL_SECONDS "$ttl"
chmod 600 "$ENV_FILE"

cat <<EOF
Passkeys enabled in $ENV_FILE
  Origin: $origin
  RP ID:  $rp_id
Backup: $backup

Validate and restart:
  docker compose run --rm backend python manage.py check
  docker compose up -d --build backend caddy
EOF
