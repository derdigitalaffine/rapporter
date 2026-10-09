#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${FAMILYOS_ENV_FILE:-$ROOT/.env}"
OPENSSL_BIN="${FAMILYOS_OPENSSL_BIN:-openssl}"

fail(){ echo "ensure-vapid: $*" >&2; exit 1; }
command -v "$OPENSSL_BIN" >/dev/null 2>&1 || fail "OpenSSL fehlt. Bitte installieren und erneut ausführen."
[[ -f "$ENV_FILE" ]] || fail "Keine .env gefunden: $ENV_FILE"

env_value(){
  local key="$1" line
  line=$(grep -m1 "^${key}=" "$ENV_FILE" 2>/dev/null || true)
  printf '%s' "${line#*=}"
}

b64url(){ "$OPENSSL_BIN" base64 -A | tr '+/' '-_' | tr -d '='; }
b64url_decode(){
  local value="$1" standard mod
  standard="${value//-/+}"; standard="${standard//_/\/}"
  mod=$((${#standard}%4))
  case "$mod" in 0) ;; 2) standard+="==" ;; 3) standard+="=" ;; *) return 1 ;; esac
  printf '%s' "$standard" | "$OPENSSL_BIN" base64 -d -A
}

pair_valid(){
  local public="$1" private="$2" tmp derived decoded_public
  [[ -n "$public" && -n "$private" ]] || return 1
  tmp=$(mktemp -d)
  if ! b64url_decode "$private" > "$tmp/private.der" 2>/dev/null; then rm -rf "$tmp"; return 1; fi
  if ! decoded_public=$(b64url_decode "$public" 2>/dev/null | wc -c | tr -d ' '); then rm -rf "$tmp"; return 1; fi
  [[ "$decoded_public" == "65" ]] || { rm -rf "$tmp"; return 1; }
  if ! derived=$("$OPENSSL_BIN" ec -inform DER -in "$tmp/private.der" -pubout -conv_form uncompressed -outform DER 2>/dev/null | tail -c 65 | b64url); then rm -rf "$tmp"; return 1; fi
  rm -rf "$tmp"
  [[ "$derived" == "$public" ]]
}

generate_pair(){
  local tmp
  tmp=$(mktemp -d)
  "$OPENSSL_BIN" ecparam -name prime256v1 -genkey -noout -out "$tmp/private.pem" 2>/dev/null
  VAPID_PRIVATE_KEY=$("$OPENSSL_BIN" ec -in "$tmp/private.pem" -outform DER 2>/dev/null | b64url)
  VAPID_PUBLIC_KEY=$("$OPENSSL_BIN" ec -in "$tmp/private.pem" -pubout -conv_form uncompressed -outform DER 2>/dev/null | tail -c 65 | b64url)
  rm -rf "$tmp"
}

set_env_value(){
  local key="$1" value="$2" tmp
  tmp=$(mktemp)
  awk -v key="$key" -v value="$value" '
    BEGIN{done=0}
    index($0,key "=")==1 {if(!done){print key "=" value; done=1}; next}
    {print}
    END{if(!done)print key "=" value}
  ' "$ENV_FILE" > "$tmp"
  cat "$tmp" > "$ENV_FILE"
  rm -f "$tmp"
}

VAPID_PUBLIC_KEY=$(env_value VAPID_PUBLIC_KEY)
VAPID_PRIVATE_KEY=$(env_value VAPID_PRIVATE_KEY)
VAPID_SUBJECT=$(env_value VAPID_SUBJECT)
DJANGO_SUPERUSER_EMAIL=$(env_value DJANGO_SUPERUSER_EMAIL)

if pair_valid "$VAPID_PUBLIC_KEY" "$VAPID_PRIVATE_KEY"; then
  echo "Web Push: vorhandenes VAPID-Schlüsselpaar ist gültig und bleibt unverändert."
  exit 0
fi

generate_pair
[[ -n "$VAPID_PUBLIC_KEY" && -n "$VAPID_PRIVATE_KEY" ]] || fail "VAPID-Schlüsselpaar konnte nicht erzeugt werden."
VAPID_SUBJECT="${VAPID_SUBJECT:-mailto:${DJANGO_SUPERUSER_EMAIL:-admin@example.com}}"
set_env_value VAPID_PUBLIC_KEY "$VAPID_PUBLIC_KEY"
set_env_value VAPID_PRIVATE_KEY "$VAPID_PRIVATE_KEY"
set_env_value VAPID_SUBJECT "$VAPID_SUBJECT"
chmod 600 "$ENV_FILE"

echo "Web Push: fehlendes oder inkonsistentes VAPID-Schlüsselpaar wurde sicher ersetzt."
echo "Hinweis: Backend neu starten, damit die neuen Umgebungswerte aktiv werden."
