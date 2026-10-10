#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${ENV_FILE:-$ROOT_DIR/.env}"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Missing $ENV_FILE. Run ./scripts/setup.sh or copy .env.example first." >&2
  exit 1
fi

set_env() {
  local key="$1" value="$2" tmp
  if [[ "$value" == *$'\n'* || "$value" == *$'\r'* ]]; then
    echo "Refusing newline in $key." >&2
    exit 1
  fi
  tmp="$(mktemp)"
  grep -v "^${key}=" "$ENV_FILE" > "$tmp" || true
  printf '%s=%s\n' "$key" "$value" >> "$tmp"
  mv "$tmp" "$ENV_FILE"
}

if [[ "${1:-}" == "--disable" ]]; then
  set_env EMAIL_BACKEND django.core.mail.backends.dummy.EmailBackend
  chmod 600 "$ENV_FILE"
  echo "Transactional email disabled (dummy backend)."
  exit 0
fi

read -r -p "SMTP host: " smtp_host
read -r -p "SMTP port [587]: " smtp_port
smtp_port="${smtp_port:-587}"
read -r -p "SMTP user (optional): " smtp_user
read -r -s -p "SMTP password (optional): " smtp_password
echo
read -r -p "From address [FamilyOS <${smtp_user:-noreply@localhost}>]: " from_address
from_address="${from_address:-FamilyOS <${smtp_user:-noreply@localhost}>}"
read -r -p "Use implicit SSL instead of STARTTLS? [y/N]: " implicit_ssl

if [[ "${implicit_ssl,,}" == "y" || "${implicit_ssl,,}" == "yes" ]]; then
  use_ssl=true
  use_tls=false
else
  use_ssl=false
  use_tls=true
fi

set_env EMAIL_BACKEND django.core.mail.backends.smtp.EmailBackend
set_env EMAIL_HOST "$smtp_host"
set_env EMAIL_PORT "$smtp_port"
set_env EMAIL_HOST_USER "$smtp_user"
set_env EMAIL_HOST_PASSWORD "$smtp_password"
set_env EMAIL_USE_TLS "$use_tls"
set_env EMAIL_USE_SSL "$use_ssl"
set_env EMAIL_TIMEOUT 10
set_env DEFAULT_FROM_EMAIL "$from_address"
set_env SERVER_EMAIL "$from_address"
chmod 600 "$ENV_FILE"

cat <<'EOF'
SMTP configuration written without echoing the password.
Validate and restart:
  docker compose run --rm backend python manage.py check --tag mailing
  docker compose up -d --build backend mail-worker
EOF
