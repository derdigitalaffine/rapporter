from django.urls import path

from .views import change_email, identity_status, resend_verification, verify_email


urlpatterns = [
    path("identity/", identity_status, name="email_identity_status"),
    path("verification/resend/", resend_verification, name="email_identity_resend"),
    path("change/", change_email, name="email_identity_change"),
    path("verify/", verify_email, name="email_identity_verify"),
]
