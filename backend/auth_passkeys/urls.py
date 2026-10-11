from django.urls import path

from .views import (
    authentication_options_view,
    authentication_verify_view,
    passkey_detail,
    passkey_list,
    reauthentication_options_view,
    reauthentication_verify_view,
    registration_options_view,
    registration_verify_view,
)

urlpatterns = [
    path("", passkey_list, name="passkey_list"),
    path("registration/options/", registration_options_view, name="passkey_registration_options"),
    path("registration/verify/", registration_verify_view, name="passkey_registration_verify"),
    path("authentication/options/", authentication_options_view, name="passkey_authentication_options"),
    path("authentication/verify/", authentication_verify_view, name="passkey_authentication_verify"),
    path("reauth/options/", reauthentication_options_view, name="passkey_reauthentication_options"),
    path("reauth/verify/", reauthentication_verify_view, name="passkey_reauthentication_verify"),
    path("<uuid:credential_id>/", passkey_detail, name="passkey_detail"),
]
