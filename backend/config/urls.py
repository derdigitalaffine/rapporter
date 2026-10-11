from django.contrib import admin
from django.urls import include, path

from auth_identity.password_reset_views import password_reset_confirm, password_reset_request
from auth_sessions.views import reauthenticate_password, revoke_other_sessions, session_detail, session_list
from family.auth_views import login_view, logout_view, refresh_view, session_view
from mailing.views import superadmin_mail_health
from mailing.superadmin_views import superadmin_smtp_config, superadmin_smtp_test

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
    path("api/superadmin/mail-health/", superadmin_mail_health, name="superadmin_mail_health"),
    path("api/superadmin/smtp/", superadmin_smtp_config, name="superadmin_smtp_config"),
    path("api/superadmin/smtp/test/", superadmin_smtp_test, name="superadmin_smtp_test"),
    path("api/", include("entitlements.urls")),
    path("api/", include("family.urls")),
    path("api/", include("expenses.urls")),
    path("api/", include("baby.urls")),
    path("api/", include("pets.urls")),
    path("api/", include("documents.urls")),
    path("api/", include("contracts.urls")),
    path("api/", include("correspondence.urls")),
    path("api/", include("decisions.urls")),
    path("api/", include("wishlists.urls")),
]
