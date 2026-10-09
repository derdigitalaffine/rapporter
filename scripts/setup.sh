#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="$ROOT/.env"
TITLE="fam-uh-le · Erstkonfiguration"

ui=""
if command -v dialog >/dev/null 2>&1; then ui=dialog
elif command -v whiptail >/dev/null 2>&1; then ui=whiptail
else
  echo "Für den Setup-Wizard wird 'dialog' oder 'whiptail' benötigt." >&2
  echo "Debian/Ubuntu: sudo apt install dialog   ·   Alpine: apk add dialog" >&2
  exit 1
fi

cleanup(){ clear 2>/dev/null || true; }
trap cleanup EXIT

box(){ "$ui" --title "$TITLE" --msgbox "$1" 14 76; }
input(){ local label="$1" default="${2:-}" out; out=$("$ui" --title "$TITLE" --inputbox "$label" 11 76 "$default" 3>&1 1>&2 2>&3) || exit 1; printf '%s' "$out"; }
password(){ local label="$1" out; out=$("$ui" --title "$TITLE" --passwordbox "$label" 10 72 3>&1 1>&2 2>&3) || exit 1; printf '%s' "$out"; }
yesno(){ "$ui" --title "$TITLE" --yesno "$1" 12 76; }
menu(){ local label="$1"; shift; "$ui" --title "$TITLE" --menu "$label" 18 82 10 "$@" 3>&1 1>&2 2>&3; }

random_secret(){
  if command -v openssl >/dev/null 2>&1; then openssl rand -base64 48 | tr -d '\n' | tr '/+' '_-'
  else python3 - <<'PY'
import secrets
print(secrets.token_urlsafe(48))
PY
  fi
}

b64url(){ openssl base64 -A | tr '+/' '-_' | tr -d '='; }
generate_vapid(){
  local tmp
  tmp=$(mktemp)
  openssl ecparam -name prime256v1 -genkey -noout -out "$tmp" 2>/dev/null
  VAPID_PRIVATE_KEY=$(openssl ec -in "$tmp" -outform DER 2>/dev/null | b64url)
  VAPID_PUBLIC_KEY=$(openssl ec -in "$tmp" -pubout -conv_form uncompressed -outform DER 2>/dev/null | tail -c 65 | b64url)
  rm -f "$tmp"
}

local_ip(){ command -v hostname >/dev/null 2>&1 && hostname -I 2>/dev/null | awk '{print $1}' || true; }
valid_port(){ [[ "$1" =~ ^[0-9]+$ ]] && (( $1 >= 1 && $1 <= 65535 )); }
valid_bind(){ [[ "$1" == "0.0.0.0" || "$1" == "127.0.0.1" || "$1" =~ ^([0-9]{1,3}\.){3}[0-9]{1,3}$ ]]; }
need(){ command -v "$1" >/dev/null 2>&1 || { box "'$1' fehlt. Bitte installieren und den Wizard erneut starten."; exit 1; }; }

need docker
if ! docker compose version >/dev/null 2>&1; then box "Docker Compose v2 wurde nicht gefunden."; exit 1; fi

if [[ -f "$ENV_FILE" ]]; then
  if ! yesno "Es existiert bereits eine .env. Möchtest du sie interaktiv überschreiben?\n\nDie bestehende Datei wird als .env.backup.TIMESTAMP gesichert."; then exit 0; fi
  cp "$ENV_FILE" "$ENV_FILE.backup.$(date +%Y%m%d-%H%M%S)"
fi

box "Willkommen bei fam-uh-le.\n\nDieser Assistent erzeugt die vollständige .env, richtet den gewünschten HTTPS-/Reverse-Proxy-Modus ein und kann den Stack direkt starten.\n\nStandardmäßig wird internes HTTPS mit Caddys lokaler CA verwendet."

TLS_MODE=$(menu "Betriebsmodus wählen" \
  internal "Self-Signed / Caddy Internal CA (LAN/erster Start)" \
  public "Öffentliches HTTPS via ACME / Let's Encrypt" \
  proxy "Plain HTTP hinter eigenem Reverse Proxy (TLS dort)")

COMPOSE_FILE="docker-compose.yml:docker-compose.override.yml"
PUBLIC_SCHEME="https"
PUBLIC_PORT=443
HTTP_BIND="0.0.0.0"
HTTPS_BIND="0.0.0.0"
HTTP_PORT=80
HTTPS_PORT=443

if [[ "$TLS_MODE" == "internal" ]]; then
  DEFAULT_HOST="$(local_ip)"; DEFAULT_HOST="${DEFAULT_HOST:-localhost}"
  DOMAIN=$(input "Hostname oder IP für den lokalen Zugriff.\nDie automatisch erkannte LAN-IP ist meist am bequemsten." "$DEFAULT_HOST")
  CADDYFILE="Caddyfile.selfsigned"
elif [[ "$TLS_MODE" == "public" ]]; then
  DOMAIN=$(input "Öffentliche Domain. DNS A/AAAA muss auf diesen Server zeigen." "fam-uh-le.example.com")
  CADDYFILE="Caddyfile"
else
  DOMAIN=$(input "Öffentliche Domain, unter der dein vorhandener Reverse Proxy fam-uh-le bereitstellt.\nDer Reverse Proxy muss HTTPS/TLS terminieren." "fam-uh-le.example.com")
  CADDYFILE="Caddyfile.proxy"
  COMPOSE_FILE="docker-compose.yml"
  HTTP_BIND="127.0.0.1"
  HTTP_PORT=8080
fi

if [[ "$TLS_MODE" == "proxy" ]]; then
  if yesno "Erweiterte Reverse-Proxy-Einstellungen öffnen?\n\nStandardmäßig lauscht fam-uh-le nur auf 127.0.0.1:8080 und belegt keinen HTTPS-Port.\nBei einem Reverse Proxy auf einem anderen Host/Container muss die Bind-Adresse erreichbar sein."; then
    while :; do
      HTTP_BIND=$(input "Bind-Adresse für den internen HTTP-Upstream.\n127.0.0.1 = nur gleicher Host, 0.0.0.0 = alle Interfaces." "$HTTP_BIND")
      valid_bind "$HTTP_BIND" && break
      box "Ungültige Bind-Adresse. Bitte IPv4-Adresse, 127.0.0.1 oder 0.0.0.0 verwenden."
    done
    while :; do HTTP_PORT=$(input "Interner HTTP-Port für deinen Reverse Proxy" "$HTTP_PORT"); valid_port "$HTTP_PORT" && break; box "Ungültiger Port. Erlaubt: 1–65535."; done
    while :; do PUBLIC_PORT=$(input "Öffentlicher HTTPS-Port am vorgeschalteten Reverse Proxy" "$PUBLIC_PORT"); valid_port "$PUBLIC_PORT" && break; box "Ungültiger Port. Erlaubt: 1–65535."; done
  fi
else
  if yesno "Erweiterte Netzwerkeinstellungen öffnen?\n\nHier kannst du die veröffentlichten HTTP-/HTTPS-Ports ändern. Intern bleibt Caddy auf 80/443."; then
    while :; do HTTP_PORT=$(input "Veröffentlichter HTTP-Port" "$HTTP_PORT"); valid_port "$HTTP_PORT" && break; box "Ungültiger Port. Erlaubt: 1–65535."; done
    while :; do HTTPS_PORT=$(input "Veröffentlichter HTTPS-Port" "$HTTPS_PORT"); valid_port "$HTTPS_PORT" && break; box "Ungültiger Port. Erlaubt: 1–65535."; done
    if [[ "$HTTP_PORT" == "$HTTPS_PORT" ]]; then box "HTTP- und HTTPS-Port dürfen nicht identisch sein."; exit 1; fi
    if [[ "$TLS_MODE" == "public" && ( "$HTTP_PORT" != "80" || "$HTTPS_PORT" != "443" ) ]]; then
      box "Hinweis zu Let's Encrypt:\n\nFür Caddys automatische ACME-Challenges müssen von außen normalerweise Port 80 und/oder 443 erreichbar sein. Abweichende Host-Ports funktionieren nur, wenn ein vorgeschalteter Router die öffentlichen Standardports passend weiterleitet."
    fi
  fi
  PUBLIC_PORT="$HTTPS_PORT"
fi

if [[ "$PUBLIC_PORT" == "443" ]]; then PUBLIC_HOST="$DOMAIN"; else PUBLIC_HOST="$DOMAIN:$PUBLIC_PORT"; fi
ORIGIN="$PUBLIC_SCHEME://$PUBLIC_HOST"
APP_URL="$ORIGIN"

TIME_ZONE=$(input "Zeitzone" "Europe/Berlin")
INITIAL_LOCALE=$(menu "Standardsprache der ersten Familie" de "Deutsch" en "English")
INITIAL_FAMILY_NAME=$(input "Name der ersten Familie" "Meine Familie")
DJANGO_SUPERUSER_USERNAME=$(input "Admin-Benutzername" "admin")
DJANGO_SUPERUSER_EMAIL=$(input "Admin-E-Mail" "admin@example.com")

if yesno "Sicheres Admin-Passwort automatisch generieren?"; then
  DJANGO_SUPERUSER_PASSWORD=$(random_secret | cut -c1-32); GENERATED_ADMIN=1
else
  while :; do
    DJANGO_SUPERUSER_PASSWORD=$(password "Admin-Passwort (mindestens 12 Zeichen)")
    [[ ${#DJANGO_SUPERUSER_PASSWORD} -ge 12 ]] && break
    box "Bitte mindestens 12 Zeichen verwenden."
  done
  GENERATED_ADMIN=0
fi

POSTGRES_DB=$(input "PostgreSQL Datenbankname" "famuhle")
POSTGRES_USER=$(input "PostgreSQL Benutzer" "famuhle")
if yesno "Datenbankpasswort automatisch generieren?"; then POSTGRES_PASSWORD=$(random_secret); else POSTGRES_PASSWORD=$(password "PostgreSQL Passwort"); fi
DJANGO_SECRET_KEY=$(random_secret)
GUNICORN_WORKERS=$(input "Gunicorn Worker (für kleine Installationen meist 2–4)" "3")
while :; do
  INTEGRATION_SYNC_SECONDS=$(input "Automatische Integrationen aktualisieren alle N Sekunden.\nEmpfehlung: 300 (5 Minuten)." "300")
  [[ "$INTEGRATION_SYNC_SECONDS" =~ ^[0-9]+$ ]] && (( INTEGRATION_SYNC_SECONDS >= 60 )) && break
  box "Bitte mindestens 60 Sekunden als ganze Zahl angeben."
done

OAUTH_CALLBACK="$ORIGIN/api/integration-oauth/callback/"
GOOGLE_OAUTH_CLIENT_ID=""
GOOGLE_OAUTH_CLIENT_SECRET=""
MICROSOFT_OAUTH_CLIENT_ID=""
MICROSOFT_OAUTH_CLIENT_SECRET=""

if yesno "Optionale Kalender-OAuth-Anbieter konfigurieren?\n\nOhne OAuth funktionieren weiterhin ICS/iCal-Kalender.\nCallback-URL für beide Anbieter:\n$OAUTH_CALLBACK"; then
  if yesno "Google Calendar OAuth aktivieren?\n\nLege in Google Cloud eine Web-OAuth-App mit calendar.readonly an und trage als Redirect-URI ein:\n$OAUTH_CALLBACK"; then
    GOOGLE_OAUTH_CLIENT_ID=$(input "Google OAuth Client-ID")
    GOOGLE_OAUTH_CLIENT_SECRET=$(password "Google OAuth Client-Secret")
  fi
  if yesno "Microsoft Outlook / Microsoft 365 OAuth aktivieren?\n\nDie App benötigt delegiertes Calendars.Read + offline_access. Redirect-URI:\n$OAUTH_CALLBACK"; then
    MICROSOFT_OAUTH_CLIENT_ID=$(input "Microsoft OAuth Client-ID")
    MICROSOFT_OAUTH_CLIENT_SECRET=$(password "Microsoft OAuth Client-Secret")
  fi
fi

VAPID_PUBLIC_KEY=""
VAPID_PRIVATE_KEY=""
VAPID_SUBJECT="mailto:${DJANGO_SUPERUSER_EMAIL:-admin@example.com}"
PUSH_STATUS="aus"
if yesno "Web-Push-Benachrichtigungen aktivieren?\n\nEmpfohlen für Warnungen, Erinnerungen und Wenn→Dann-Regeln. Pro Gerät ist später eine einmalige Zustimmung im Browser nötig."; then
  if command -v openssl >/dev/null 2>&1; then
    generate_vapid
    PUSH_STATUS="konfiguriert"
  else
    box "OpenSSL fehlt. Web Push bleibt deaktiviert.\n\nNach Installation von openssl kannst du das Setup erneut ausführen."
  fi
fi

GOOGLE_STATUS="aus"
MICROSOFT_STATUS="aus"
[[ -n "$GOOGLE_OAUTH_CLIENT_ID" ]] && GOOGLE_STATUS="konfiguriert"
[[ -n "$MICROSOFT_OAUTH_CLIENT_ID" ]] && MICROSOFT_STATUS="konfiguriert"

if [[ "$TLS_MODE" == "proxy" ]]; then
  NETWORK_SUMMARY="Lokaler TLS/SSL-Listener: aus\nReverse-Proxy-Upstream: http://$HTTP_BIND:$HTTP_PORT\nÖffentliche App-URL: $APP_URL"
else
  NETWORK_SUMMARY="HTTP-Port: $HTTP_PORT\nHTTPS-Port: $HTTPS_PORT\nApp-URL: $APP_URL"
fi
SUMMARY="Modus: $TLS_MODE\nHost: $DOMAIN\n$NETWORK_SUMMARY\nZeitzone: $TIME_ZONE\nSprache: $INITIAL_LOCALE\nFamilie: $INITIAL_FAMILY_NAME\nAdmin: $DJANGO_SUPERUSER_USERNAME ($DJANGO_SUPERUSER_EMAIL)\nDatenbank: $POSTGRES_DB / $POSTGRES_USER\nWorker: $GUNICORN_WORKERS\nIntegrations-Sync: alle $INTEGRATION_SYNC_SECONDS Sekunden\nGoogle OAuth: $GOOGLE_STATUS\nMicrosoft OAuth: $MICROSOFT_STATUS\nWeb Push: $PUSH_STATUS\n\nSecrets werden in .env geschrieben und hier absichtlich nicht angezeigt."
if ! yesno "$SUMMARY\n\nKonfiguration schreiben?"; then exit 0; fi

cat > "$ENV_FILE" <<EOF
# Generated by scripts/setup.sh on $(date -Iseconds)
TLS_MODE=$TLS_MODE
COMPOSE_FILE=$COMPOSE_FILE
CADDYFILE=$CADDYFILE
DOMAIN=$DOMAIN
PUBLIC_SCHEME=$PUBLIC_SCHEME
PUBLIC_HOST=$PUBLIC_HOST
PUBLIC_PORT=$PUBLIC_PORT
APP_URL=$APP_URL
HTTP_BIND=$HTTP_BIND
HTTP_PORT=$HTTP_PORT
HTTPS_BIND=$HTTPS_BIND
HTTPS_PORT=$HTTPS_PORT
DJANGO_SECRET_KEY=$DJANGO_SECRET_KEY
DJANGO_DEBUG=false
DJANGO_ALLOWED_HOSTS=$DOMAIN,backend,localhost,127.0.0.1
CSRF_TRUSTED_ORIGINS=$ORIGIN
CORS_ALLOWED_ORIGINS=$ORIGIN
TIME_ZONE=$TIME_ZONE
INITIAL_LOCALE=$INITIAL_LOCALE

POSTGRES_DB=$POSTGRES_DB
POSTGRES_USER=$POSTGRES_USER
POSTGRES_PASSWORD=$POSTGRES_PASSWORD

DJANGO_SUPERUSER_USERNAME=$DJANGO_SUPERUSER_USERNAME
DJANGO_SUPERUSER_EMAIL=$DJANGO_SUPERUSER_EMAIL
DJANGO_SUPERUSER_PASSWORD=$DJANGO_SUPERUSER_PASSWORD
INITIAL_FAMILY_NAME=$INITIAL_FAMILY_NAME
GUNICORN_WORKERS=$GUNICORN_WORKERS
INTEGRATION_SYNC_SECONDS=$INTEGRATION_SYNC_SECONDS

# Optional read-only calendar OAuth. Leave blank to use ICS/iCal only.
GOOGLE_OAUTH_CLIENT_ID=$GOOGLE_OAUTH_CLIENT_ID
GOOGLE_OAUTH_CLIENT_SECRET=$GOOGLE_OAUTH_CLIENT_SECRET
MICROSOFT_OAUTH_CLIENT_ID=$MICROSOFT_OAUTH_CLIENT_ID
MICROSOFT_OAUTH_CLIENT_SECRET=$MICROSOFT_OAUTH_CLIENT_SECRET

# Optional Web Push (generated by setup).
VAPID_PUBLIC_KEY=$VAPID_PUBLIC_KEY
VAPID_PRIVATE_KEY=$VAPID_PRIVATE_KEY
VAPID_SUBJECT=$VAPID_SUBJECT
EOF
chmod 600 "$ENV_FILE"

if [[ "$GENERATED_ADMIN" == 1 ]]; then
  "$ui" --title "$TITLE" --msgbox "Das Admin-Passwort wurde generiert. Bitte jetzt sicher speichern:\n\n$DJANGO_SUPERUSER_PASSWORD\n\nEs steht ebenfalls in .env (Dateirechte 600)." 14 76
fi

if yesno "Konfiguration gespeichert.\n\nDocker-Images jetzt bauen und fam-uh-le starten?"; then
  clear
  cd "$ROOT"
  docker compose up -d --build
  echo
  echo "fam-uh-le öffentlich: $APP_URL"
  echo "Status: docker compose ps"
  echo "Logs:   docker compose logs -f"
  echo "Backup: bash scripts/backup.sh"
  if [[ -n "$GOOGLE_OAUTH_CLIENT_ID" || -n "$MICROSOFT_OAUTH_CLIENT_ID" ]]; then
    echo "OAuth Callback: $OAUTH_CALLBACK"
  fi
  if [[ "$TLS_MODE" == "internal" ]]; then
    echo
    echo "Internal-CA aktiv. Browser zeigen zunächst eine Vertrauenswarnung, bis die lokale CA installiert ist."
    echo "CA exportieren: bash scripts/export-caddy-ca.sh"
    echo "Später öffentliches TLS: bash scripts/tls-mode.sh public"
    echo "Hinter eigenen Reverse Proxy wechseln: bash scripts/tls-mode.sh proxy"
  elif [[ "$TLS_MODE" == "proxy" ]]; then
    echo
    echo "fam-uh-le terminiert selbst kein TLS/SSL und veröffentlicht keinen Port 443."
    echo "Reverse-Proxy-Upstream: http://$HTTP_BIND:$HTTP_PORT"
    echo "Der vorgeschaltete Reverse Proxy muss HTTPS für $PUBLIC_HOST terminieren."
    if [[ "$HTTP_BIND" == "127.0.0.1" ]]; then
      echo "Hinweis: 127.0.0.1 ist nur von einem Reverse Proxy auf demselben Host erreichbar."
    else
      echo "Hinweis: Schütze den HTTP-Upstream per Firewall/Netzsegment vor direktem Internetzugriff."
    fi
  fi
else
  if [[ "$TLS_MODE" == "proxy" ]]; then
    box "Konfiguration gespeichert.\n\nStart später mit:\n  docker compose up -d --build\n\nReverse-Proxy-Upstream: http://$HTTP_BIND:$HTTP_PORT\nÖffentlich: $APP_URL"
  else
    box "Konfiguration gespeichert.\n\nStart später mit:\n  docker compose up -d --build\n\nDanach: $APP_URL"
  fi
fi
