from django.contrib import admin
from django.urls import include, path

from auth_identity.password_reset_views import password_reset_confirm, password_reset_request
from auth_sessions.admin_views import (
    superadmin_login,
    superadmin_logout,
    superadmin_reauthenticate_password,
    superadmin_refresh,
    superadmin_session,
    superadmin_sessions,
)
from auth_sessions.views import reauthenticate_password, revoke_other_sessions, session_detail, session_list
from family.auth_views import login_view, logout_view, refresh_view, session_view
from family.superadmin_analytics_views import superadmin_matomo_report, superadmin_matomo_status
from family.superadmin_user_crud_views import superadmin_user_crud_detail, superadmin_users_crud
from family.superadmin_user_views import (
    superadmin_user_email_change,
    superadmin_user_email_direct,
    superadmin_user_password_reset,
    superadmin_user_password_reset_link,
)
from mailing.views import superadmin_mail_health, superadmin_mail_journal
from mailing.superadmin_views import superadmin_smtp_config, superadmin_smtp_test
from telemetry.superadmin_audit_views import superadmin_audit_events
from telemetry.superadmin_delivery_views import superadmin_delivery_summary
from telemetry.superadmin_operations_views import superadmin_operations_health
from telemetry.superadmin_views import superadmin_analytics_overview, superadmin_security_summary

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/auth/login/", login_view, name="auth_login"),
    path("api/auth/refresh/", refresh_view, name="auth_refresh"),
    path("api/auth/logout/", logout_view, name="auth_logout"),
    path("api/auth/password-reset/request/", password_reset_request, name="auth_password_reset_request"),
    path("api/auth/password-reset/confirm/", password_reset_confirm, name="auth_password_reset_confirm"),
    path("api/auth/session/", session_view, name="auth_session"),
    path("api/auth/sessions/", session_list, name="auth_session_list"),
    path("api/auth/sessions/<uuid:sid>/", session_detail, name="auth_session_detail"),
    path("api/auth/sessions/revoke-others/", revoke_other_sessions, name="auth_session_revoke_others"),
    path("api/auth/reauth/password/", reauthenticate_password, name="auth_reauth_password"),
    path("api/auth/email/", include("auth_identity.urls")),
    path("api/auth/passkeys/", include("auth_passkeys.urls")),
    path("api/superadmin/auth/login/", superadmin_login, name="superadmin_auth_login"),
    path("api/superadmin/auth/refresh/", superadmin_refresh, name="superadmin_auth_refresh"),
    path("api/superadmin/auth/logout/", superadmin_logout, name="superadmin_auth_logout"),
    path("api/superadmin/auth/session/", superadmin_session, name="superadmin_auth_session"),
    path("api/superadmin/auth/sessions/", superadmin_sessions, name="superadmin_auth_sessions"),
    path("api/superadmin/auth/reauth/password/", superadmin_reauthenticate_password, name="superadmin_auth_reauth_password"),
    path("api/superadmin/analytics/overview/", superadmin_analytics_overview, name="superadmin_analytics_overview"),
    path("api/superadmin/analytics/matomo/status/", superadmin_matomo_status, name="superadmin_matomo_status"),
    path("api/superadmin/analytics/matomo/report/", superadmin_matomo_report, name="superadmin_matomo_report"),
    path("api/superadmin/audit/", superadmin_audit_events, name="superadmin_audit_events"),
    path("api/superadmin/security/summary/", superadmin_security_summary, name="superadmin_security_summary"),
    path("api/superadmin/delivery/summary/", superadmin_delivery_summary, name="superadmin_delivery_summary"),
    path("api/superadmin/operations/health/", superadmin_operations_health, name="superadmin_operations_health"),
    path("api/superadmin/users/", superadmin_users_crud, name="superadmin_users"),
    path("api/superadmin/users/<int:user_id>/", superadmin_user_crud_detail, name="superadmin_user_detail"),
    path("api/superadmin/users/<int:user_id>/email-change/", superadmin_user_email_change, name="superadmin_user_email_change"),
    path("api/superadmin/users/<int:user_id>/email-direct/", superadmin_user_email_direct, name="superadmin_user_email_direct"),
    path("api/superadmin/users/<int:user_id>/password-reset/", superadmin_user_password_reset, name="superadmin_user_password_reset"),
    path("api/superadmin/users/<int:user_id>/password-reset-link/", superadmin_user_password_reset_link, name="superadmin_user_password_reset_link"),
    path("api/superadmin/mail-health/", superadmin_mail_health, name="superadmin_mail_health"),
    path("api/superadmin/mail-journal/", superadmin_mail_journal, name="superadmin_mail_journal"),
    path("api/superadmin/smtp/", superadmin_smtp_config, name="superadmin_smtp_config"),
    path("api/superadmin/smtp/test/", superadmin_smtp_test, name="superadmin_smtp_test"),
    path("api/", include("telemetry.urls")),
    path("api/", include("entitlements.urls")),
    path("api/", include("family.urls")),
    path("api/", include("expenses.urls")),
    path("api/", include("vehicles.urls")),
    path("api/", include("baby.urls")),
    path("api/", include("pets.urls")),
    path("api/", include("documents.urls")),
    path("api/", include("contracts.urls")),
    path("api/", include("correspondence.urls")),
    path("api/", include("decisions.urls")),
    path("api/", include("wishlists.urls")),
    path("api/", include("notifications.urls")),
    path("api/", include("games.urls")),
]
