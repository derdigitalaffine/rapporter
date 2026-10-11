#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPT="$ROOT_DIR/scripts/configure-passkeys.sh"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

value() {
  local file="$1" key="$2"
  grep "^${key}=" "$file" | tail -n1 | cut -d= -f2-
}

assert_eq() {
  local expected="$1" actual="$2" label="$3"
  if [[ "$expected" != "$actual" ]]; then
    echo "FAIL: $label: expected '$expected', got '$actual'" >&2
    exit 1
  fi
}

case_https_upgrade() {
  local env="$TMP_DIR/https.env"
  cat > "$env" <<'EOF'
PUBLIC_SCHEME=https
PUBLIC_HOST=family.example.com
APP_URL=https://family.example.com
DJANGO_SECRET_KEY=keep-me
EOF

  ENV_FILE="$env" bash "$SCRIPT" >/dev/null
  assert_eq true "$(value "$env" WEBAUTHN_ENABLED)" "https enable"
  assert_eq family.example.com "$(value "$env" WEBAUTHN_RP_ID)" "https rp id"
  assert_eq FamilyOS "$(value "$env" WEBAUTHN_RP_NAME)" "https rp name"
  assert_eq https://family.example.com "$(value "$env" WEBAUTHN_ORIGIN)" "https origin"
  assert_eq 300 "$(value "$env" WEBAUTHN_CHALLENGE_TTL_SECONDS)" "https ttl"
  assert_eq keep-me "$(value "$env" DJANGO_SECRET_KEY)" "unrelated env preserved"

  local before backups_before backups_after
  before="$(sha256sum "$env" | cut -d' ' -f1)"
  backups_before="$(find "$TMP_DIR" -maxdepth 1 -name 'https.env.backup.passkeys.*' | wc -l)"
  ENV_FILE="$env" bash "$SCRIPT" >/dev/null
  backups_after="$(find "$TMP_DIR" -maxdepth 1 -name 'https.env.backup.passkeys.*' | wc -l)"
  assert_eq "$before" "$(sha256sum "$env" | cut -d' ' -f1)" "idempotent env"
  assert_eq "$backups_before" "$backups_after" "idempotent backup"
}

case_parent_rp_preserved() {
  local env="$TMP_DIR/parent.env"
  cat > "$env" <<'EOF'
APP_URL=https://family.example.com
WEBAUTHN_RP_ID=example.com
WEBAUTHN_RP_NAME=Meine Familie
WEBAUTHN_CHALLENGE_TTL_SECONDS=180
EOF
  ENV_FILE="$env" bash "$SCRIPT" >/dev/null
  assert_eq example.com "$(value "$env" WEBAUTHN_RP_ID)" "parent rp id preserved"
  assert_eq "Meine Familie" "$(value "$env" WEBAUTHN_RP_NAME)" "rp name preserved"
  assert_eq 180 "$(value "$env" WEBAUTHN_CHALLENGE_TTL_SECONDS)" "ttl preserved"
}

case_localhost_http() {
  local env="$TMP_DIR/localhost.env"
  cat > "$env" <<'EOF'
APP_URL=http://localhost:8080
EOF
  ENV_FILE="$env" bash "$SCRIPT" >/dev/null
  assert_eq localhost "$(value "$env" WEBAUTHN_RP_ID)" "localhost rp id"
  assert_eq http://localhost:8080 "$(value "$env" WEBAUTHN_ORIGIN)" "localhost origin"
}

case_reject_ip_without_changes() {
  local env="$TMP_DIR/ip.env" before
  cat > "$env" <<'EOF'
APP_URL=https://192.168.1.20
DJANGO_SECRET_KEY=keep-me
EOF
  before="$(sha256sum "$env" | cut -d' ' -f1)"
  if ENV_FILE="$env" bash "$SCRIPT" >/dev/null 2>&1; then
    echo "FAIL: IPv4 origin must be rejected" >&2
    exit 1
  fi
  assert_eq "$before" "$(sha256sum "$env" | cut -d' ' -f1)" "rejected IP leaves env unchanged"
}

case_reject_plain_http() {
  local env="$TMP_DIR/http.env"
  cat > "$env" <<'EOF'
APP_URL=http://family.example.com
EOF
  if ENV_FILE="$env" bash "$SCRIPT" >/dev/null 2>&1; then
    echo "FAIL: non-local HTTP origin must be rejected" >&2
    exit 1
  fi
}

case_https_upgrade
case_parent_rp_preserved
case_localhost_http
case_reject_ip_without_changes
case_reject_plain_http

echo "Passkey env upgrade tests passed."
