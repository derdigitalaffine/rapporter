#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
ENV_FILE="$TMP/.env"

value(){ local key="$1" line; line=$(grep -m1 "^${key}=" "$ENV_FILE" || true); printf '%s' "${line#*=}"; }
assert_nonempty(){ [[ -n "$(value "$1")" ]] || { echo "expected $1 to be set" >&2; exit 1; }; }

cat > "$ENV_FILE" <<'EOF'
DJANGO_SUPERUSER_EMAIL=admin@example.test
VAPID_PUBLIC_KEY=
VAPID_PRIVATE_KEY=
VAPID_SUBJECT=
EOF
chmod 644 "$ENV_FILE"
FAMILYOS_ENV_FILE="$ENV_FILE" bash "$ROOT/scripts/ensure-vapid.sh" >/dev/null
assert_nonempty VAPID_PUBLIC_KEY
assert_nonempty VAPID_PRIVATE_KEY
[[ "$(value VAPID_SUBJECT)" == "mailto:admin@example.test" ]] || { echo "unexpected VAPID_SUBJECT" >&2; exit 1; }
[[ "$(stat -c '%a' "$ENV_FILE")" == "600" ]] || { echo ".env permissions are not 600" >&2; exit 1; }

PUBLIC_ONE=$(value VAPID_PUBLIC_KEY)
PRIVATE_ONE=$(value VAPID_PRIVATE_KEY)
FAMILYOS_ENV_FILE="$ENV_FILE" bash "$ROOT/scripts/ensure-vapid.sh" >/dev/null
[[ "$(value VAPID_PUBLIC_KEY)" == "$PUBLIC_ONE" ]] || { echo "valid public key rotated" >&2; exit 1; }
[[ "$(value VAPID_PRIVATE_KEY)" == "$PRIVATE_ONE" ]] || { echo "valid private key rotated" >&2; exit 1; }

# A partial pair must be replaced together rather than leaving mismatched identity.
awk -v value="$PUBLIC_ONE" 'BEGIN{done=0} /^VAPID_PUBLIC_KEY=/{print "VAPID_PUBLIC_KEY=" value; done=1; next} /^VAPID_PRIVATE_KEY=/{print "VAPID_PRIVATE_KEY="; next} {print}' "$ENV_FILE" > "$TMP/partial"
cat "$TMP/partial" > "$ENV_FILE"
FAMILYOS_ENV_FILE="$ENV_FILE" bash "$ROOT/scripts/ensure-vapid.sh" >/dev/null
assert_nonempty VAPID_PUBLIC_KEY
assert_nonempty VAPID_PRIVATE_KEY
[[ "$(value VAPID_PUBLIC_KEY)" != "$PUBLIC_ONE" || "$(value VAPID_PRIVATE_KEY)" != "$PRIVATE_ONE" ]] || { echo "partial pair was not replaced" >&2; exit 1; }
PUBLIC_TWO=$(value VAPID_PUBLIC_KEY)
PRIVATE_TWO=$(value VAPID_PRIVATE_KEY)
FAMILYOS_ENV_FILE="$ENV_FILE" bash "$ROOT/scripts/ensure-vapid.sh" >/dev/null
[[ "$(value VAPID_PUBLIC_KEY)" == "$PUBLIC_TWO" && "$(value VAPID_PRIVATE_KEY)" == "$PRIVATE_TWO" ]] || { echo "replacement pair is not stable" >&2; exit 1; }

# Existing valid identity with a missing subject keeps its keys and only backfills the subject.
sed -i 's/^VAPID_SUBJECT=.*/VAPID_SUBJECT=/' "$ENV_FILE"
FAMILYOS_ENV_FILE="$ENV_FILE" bash "$ROOT/scripts/ensure-vapid.sh" >/dev/null
[[ "$(value VAPID_PUBLIC_KEY)" == "$PUBLIC_TWO" && "$(value VAPID_PRIVATE_KEY)" == "$PRIVATE_TWO" ]] || { echo "subject repair rotated keys" >&2; exit 1; }
[[ "$(value VAPID_SUBJECT)" == "mailto:admin@example.test" ]] || { echo "subject was not repaired" >&2; exit 1; }

if FAMILYOS_ENV_FILE="$ENV_FILE" FAMILYOS_OPENSSL_BIN="$TMP/does-not-exist" bash "$ROOT/scripts/ensure-vapid.sh" >/dev/null 2>&1; then
  echo "missing OpenSSL must fail" >&2
  exit 1
fi

if grep -q 'Web-Push-Benachrichtigungen aktivieren' "$ROOT/scripts/setup.sh"; then
  echo "setup still asks optional push question" >&2
  exit 1
fi
grep -q '^need openssl$' "$ROOT/scripts/setup.sh" || { echo "setup must require OpenSSL" >&2; exit 1; }
grep -q 'Web Push: serverseitig vorbereitet' "$ROOT/scripts/setup.sh" || { echo "setup summary must report prepared web push" >&2; exit 1; }

echo "VAPID setup checks passed"
