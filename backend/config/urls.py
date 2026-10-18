from django.contrib import admin
from django.urls import include, path
from django.views.decorators.csrf import csrf_exempt

from auth_identity.password_reset_views import password_reset_confirm, password_reset_request
from auth_sessions.admin_security_views import (
    superadmin_passkey_detail,
    superadmin_passkey_reauthentication_options,
    superadmin_passkey_reauthentication_verify,
    superadmin_passkey_registration_options,
    superadmin_passkey_registration_verify,
    superadmin_passkeys,
    superadmin_password_change,
)
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
from family.shopping_reference_operator_views import (
    superadmin_reference_dataset_action,
    superadmin_reference_dataset_detail,
    superadmin_reference_dataset_validate,
    superadmin_reference_datasets,
)
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

from family.sync_views import sync

from family.calendar_subscription_views import subscriptions, subscription_detail
from family.calendar_subscription_dav import feed, well_known
from family.calendar_subscription_scheduling import dav
from family.calendar_subscription_member_feed import member_feed

urlpatterns = [
    path(".well-known/caldav", csrf_exempt(well_known)),
    path("caldav/", dav),
    path("caldav/<path:path>", dav),
    path("calendar-feed/<str:token>/family.ics", feed),
    path("calendar-feed/<str:token>/member/<uuid:member_id>.ics", member_feed),
    path("api/calendar-subscriptions/<uuid:family_id>/", subscriptions),
    path("api/calendar-subscriptions/<uuid:family_id>/<uuid:subscription_id>/", subscription_detail),
    path("api/calendar-subscriptions/<uuid:family_id>/<uuid:subscription_id>/<str:operation>/", subscription_detail),
    path("api/sync/", sync, name="offline_sync"),
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
    path("api/superadmin/auth/reauth/passkey/options/", superadmin_passkey_reauthentication_options, name="superadmin_auth_reauth_passkey_options"),
    path("api/superadmin/auth/reauth/passkey/verify/", superadmin_passkey_reauthentication_verify, name="superadmin_auth_reauth_passkey_verify"),
    path("api/superadmin/auth/passkeys/", superadmin_passkeys, name="superadmin_auth_passkeys"),
    path("api/superadmin/auth/passkeys/register/options/", superadmin_passkey_registration_options, name="superadmin_auth_passkey_register_options"),
    path("api/superadmin/auth/passkeys/register/verify/", superadmin_passkey_registration_verify, name="superadmin_auth_passkey_register_verify"),
    path("api/superadmin/auth/passkeys/<uuid:credential_id>/", superadmin_passkey_detail, name="superadmin_auth_passkey_detail"),
    path("api/superadmin/auth/password/", superadmin_password_change, name="superadmin_auth_password_change"),
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
    path("api/superadmin/reference-datasets/", superadmin_reference_datasets, name="superadmin_reference_datasets"),
    path("api/superadmin/reference-datasets/validate/", superadmin_reference_dataset_validate, name="superadmin_reference_dataset_validate"),
    path("api/superadmin/reference-datasets/<uuid:dataset_pk>/", superadmin_reference_dataset_detail, name="superadmin_reference_dataset_detail"),
    path("api/superadmin/reference-datasets/<uuid:dataset_pk>/<str:action>/", superadmin_reference_dataset_action, name="superadmin_reference_dataset_action"),
    path("api/superadmin/mail-health/", superadmin_mail_health, name="superadmin_mail_health"),
    path("api/superadmin/mail-journal/", superadmin_mail_journal, name="superadmin_mail_journal"),
    path("api/superadmin/smtp/", superadmin_smtp_config, name="superadmin_smtp_config"),
    path("api/superadmin/smtp/test/", superadmin_smtp_test, name="superadmin_smtp_test"),
    path("api/", include("telemetry.urls")),
    path("api/", include("entitlements.urls")),
    path("api/", include("family_statistics.urls")),
    path("api/", include("family.meal_urls")),
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
    path("api/chat/", include("messenger.urls")),
]
