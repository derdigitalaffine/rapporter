import os
from pathlib import Path
from datetime import timedelta


def env_bool(name, default=False):
    fallback = "true" if default else "false"
    return os.getenv(name, fallback).strip().lower() in {"1", "true", "yes", "on"}


BASE_DIR=Path(__file__).resolve().parent.parent
SECRET_KEY=os.getenv("DJANGO_SECRET_KEY","dev-only-change-me");DEBUG=env_bool("DJANGO_DEBUG",False);ALLOWED_HOSTS=[h.strip() for h in os.getenv("DJANGO_ALLOWED_HOSTS","localhost,127.0.0.1").split(",") if h.strip()];CSRF_TRUSTED_ORIGINS=[u.strip() for u in os.getenv("CSRF_TRUSTED_ORIGINS","").split(",") if u.strip()]
INSTALLED_APPS=["django.contrib.admin","django.contrib.auth","django.contrib.contenttypes","django.contrib.sessions","django.contrib.messages","django.contrib.staticfiles","django.contrib.postgres","corsheaders","rest_framework","auth_abuse.apps.AuthAbuseConfig","auth_identity.apps.AuthIdentityConfig","auth_sessions.apps.AuthSessionsConfig","auth_passkeys.apps.AuthPasskeysConfig","entitlements.apps.EntitlementsConfig","telemetry.apps.TelemetryConfig","family","expenses","baby.apps.BabyConfig","pets.apps.PetsConfig","documents.apps.DocumentsConfig","contracts.apps.ContractsConfig","correspondence.apps.CorrespondenceConfig","decisions.apps.DecisionsConfig","wishlists.apps.WishlistsConfig","notifications.apps.NotificationsConfig","mailing.apps.MailingConfig"]
MIDDLEWARE=["django.middleware.security.SecurityMiddleware","whitenoise.middleware.WhiteNoiseMiddleware","corsheaders.middleware.CorsMiddleware","django.contrib.sessions.middleware.SessionMiddleware","django.middleware.common.CommonMiddleware","django.middleware.csrf.CsrfViewMiddleware","django.contrib.auth.middleware.AuthenticationMiddleware","family.request_context.ActorContextMiddleware","baby.middleware.PrivateBabyNoStoreMiddleware","pets.middleware.PrivatePetNoStoreMiddleware","django.contrib.messages.middleware.MessageMiddleware","django.middleware.clickjacking.XFrameOptionsMiddleware"]
ROOT_URLCONF="config.urls";TEMPLATES=[{"BACKEND":"django.template.backends.django.DjangoTemplates","DIRS":[],"APP_DIRS":True,"OPTIONS":{"context_processors":["django.template.context_processors.request","django.contrib.auth.context_processors.auth","django.contrib.messages.context_processors.messages"]}}];WSGI_APPLICATION="config.wsgi.application"
DATABASES={"default":{"ENGINE":"django.db.backends.postgresql","NAME":os.getenv("POSTGRES_DB","famuhle"),"USER":os.getenv("POSTGRES_USER","famuhle"),"PASSWORD":os.getenv("POSTGRES_PASSWORD","famuhle"),"HOST":os.getenv("POSTGRES_HOST","db"),"PORT":os.getenv("POSTGRES_PORT","5432")}}
AUTH_PASSWORD_VALIDATORS=[{"NAME":"django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},{"NAME":"django.contrib.auth.password_validation.MinimumLengthValidator"},{"NAME":"django.contrib.auth.password_validation.CommonPasswordValidator"},{"NAME":"django.contrib.auth.password_validation.NumericPasswordValidator"}]
LANGUAGE_CODE="de";LANGUAGES=[("de","Deutsch"),("en","English")];TIME_ZONE=os.getenv("TIME_ZONE","Europe/Berlin");USE_I18N=True;USE_TZ=True
STATIC_URL="/static/";STATIC_ROOT=BASE_DIR/"staticfiles";MEDIA_ROOT=Path(os.getenv("MEDIA_ROOT",BASE_DIR/"media"));DEFAULT_AUTO_FIELD="django.db.models.BigAutoField"
REST_FRAMEWORK={"DEFAULT_AUTHENTICATION_CLASSES":("family.authentication.CookieJWTAuthentication",),"DEFAULT_PERMISSION_CLASSES":("family.permissions.ActiveTenantAccess",),"DEFAULT_FILTER_BACKENDS":("family.filters.ActiveTenantFilterBackend",),"DEFAULT_PAGINATION_CLASS":"rest_framework.pagination.PageNumberPagination","PAGE_SIZE":100}
SIMPLE_JWT={"ACCESS_TOKEN_LIFETIME":timedelta(minutes=30),"REFRESH_TOKEN_LIFETIME":timedelta(days=30),"ROTATE_REFRESH_TOKENS":True,"BLACKLIST_AFTER_ROTATION":False}
AUTH_ABUSE_HMAC_KEY=os.getenv("AUTH_ABUSE_HMAC_KEY") or SECRET_KEY;AUTH_TRUSTED_PROXY_CIDRS=[value.strip() for value in os.getenv("AUTH_TRUSTED_PROXY_CIDRS","").split(",") if value.strip()];AUTH_ABUSE_IPV4_PREFIX=int(os.getenv("AUTH_ABUSE_IPV4_PREFIX","32"));AUTH_ABUSE_IPV6_PREFIX=int(os.getenv("AUTH_ABUSE_IPV6_PREFIX","64"));AUTH_ABUSE_RETENTION_SECONDS=int(os.getenv("AUTH_ABUSE_RETENTION_SECONDS","86400"))
AUTH_SESSION_ABSOLUTE_DAYS=int(os.getenv("AUTH_SESSION_ABSOLUTE_DAYS","90"));AUTH_SESSION_FRESH_SECONDS=int(os.getenv("AUTH_SESSION_FRESH_SECONDS","600"));AUTH_SESSION_REFRESH_REUSE_GRACE_SECONDS=int(os.getenv("AUTH_SESSION_REFRESH_REUSE_GRACE_SECONDS","5"));AUTH_SESSION_SEEN_WRITE_SECONDS=int(os.getenv("AUTH_SESSION_SEEN_WRITE_SECONDS","300"));AUTH_SESSION_RETENTION_DAYS=int(os.getenv("AUTH_SESSION_RETENTION_DAYS","30"))
WEBAUTHN_ENABLED=env_bool("WEBAUTHN_ENABLED",False);WEBAUTHN_RP_ID=os.getenv("WEBAUTHN_RP_ID","").strip();WEBAUTHN_RP_NAME=os.getenv("WEBAUTHN_RP_NAME","FamilyOS").strip();WEBAUTHN_ORIGIN=os.getenv("WEBAUTHN_ORIGIN","").strip().rstrip("/");WEBAUTHN_CHALLENGE_TTL_SECONDS=int(os.getenv("WEBAUTHN_CHALLENGE_TTL_SECONDS","300"))
EMAIL_VERIFICATION_MAX_AGE_SECONDS=int(os.getenv("EMAIL_VERIFICATION_MAX_AGE_SECONDS","86400"));EMAIL_VERIFICATION_RESEND_COOLDOWN_SECONDS=int(os.getenv("EMAIL_VERIFICATION_RESEND_COOLDOWN_SECONDS","60"))
PASSWORD_RESET_TIMEOUT=int(os.getenv("PASSWORD_RESET_TIMEOUT","3600"));PASSWORD_RESET_RESEND_COOLDOWN_SECONDS=int(os.getenv("PASSWORD_RESET_RESEND_COOLDOWN_SECONDS","60"))
TELEMETRY_USAGE_RETENTION_DAYS=int(os.getenv("TELEMETRY_USAGE_RETENTION_DAYS","60"));TELEMETRY_AUDIT_RETENTION_DAYS=int(os.getenv("TELEMETRY_AUDIT_RETENTION_DAYS","180"))
CORS_ALLOWED_ORIGINS=[u.strip() for u in os.getenv("CORS_ALLOWED_ORIGINS","http://localhost:5173").split(",") if u.strip()];CORS_ALLOW_CREDENTIALS=True;SECURE_PROXY_SSL_HEADER=("HTTP_X_FORWARDED_PROTO","https");SESSION_COOKIE_SECURE=not DEBUG;SESSION_COOKIE_HTTPONLY=True;SESSION_COOKIE_SAMESITE="Lax";CSRF_COOKIE_SECURE=not DEBUG;CSRF_COOKIE_SAMESITE="Lax";SECURE_HSTS_SECONDS=0 if DEBUG else 31536000;SECURE_HSTS_INCLUDE_SUBDOMAINS=not DEBUG;SECURE_HSTS_PRELOAD=not DEBUG;SECURE_CONTENT_TYPE_NOSNIFF=True;SECURE_REFERRER_POLICY="same-origin";X_FRAME_OPTIONS="DENY"

# Transactional mail platform. Deployment configuration remains the fallback; the
# routing backend switches to encrypted Superadmin SMTP only when explicitly enabled.
APP_URL=os.getenv("APP_URL","").strip().rstrip("/")
EMAIL_ENV_BACKEND=os.getenv("EMAIL_BACKEND","django.core.mail.backends.dummy.EmailBackend").strip()
EMAIL_BACKEND="mailing.backends.ManagedRoutingEmailBackend"
EMAIL_HOST=os.getenv("EMAIL_HOST","").strip()
EMAIL_PORT=int(os.getenv("EMAIL_PORT","587") or "587")
EMAIL_HOST_USER=os.getenv("EMAIL_HOST_USER","")
EMAIL_HOST_PASSWORD=os.getenv("EMAIL_HOST_PASSWORD","")
EMAIL_USE_TLS=env_bool("EMAIL_USE_TLS",True)
EMAIL_USE_SSL=env_bool("EMAIL_USE_SSL",False)
EMAIL_TIMEOUT=float(os.getenv("EMAIL_TIMEOUT","10") or "10")
DEFAULT_FROM_EMAIL=os.getenv("DEFAULT_FROM_EMAIL","FamilyOS <noreply@localhost>").strip()
SERVER_EMAIL=os.getenv("SERVER_EMAIL",DEFAULT_FROM_EMAIL).strip()
EMAIL_REPLY_TO=os.getenv("EMAIL_REPLY_TO","").strip()

# Optional external Matomo reporting integration. The auth token is backend-only
# and must never be exposed to the Superadmin frontend or browser tracking code.
MATOMO_BASE_URL=os.getenv("MATOMO_BASE_URL","").strip().rstrip("/")
MATOMO_SITE_ID=os.getenv("MATOMO_SITE_ID","").strip()
MATOMO_AUTH_TOKEN=os.getenv("MATOMO_AUTH_TOKEN","").strip()
MATOMO_API_TIMEOUT=float(os.getenv("MATOMO_API_TIMEOUT","8") or "8")

# Optional privacy-bounded Matomo product tracking. Disabled by default. Tracking
# is server-to-server; the browser never receives Matomo credentials or origins.
MATOMO_TRACKING_ENABLED=env_bool("MATOMO_TRACKING_ENABLED",False)
MATOMO_TRACKING_APP_ORIGIN=(os.getenv("MATOMO_TRACKING_APP_ORIGIN","").strip().rstrip("/") or APP_URL)
MATOMO_TRACKING_TIMEOUT=float(os.getenv("MATOMO_TRACKING_TIMEOUT","4") or "4")
