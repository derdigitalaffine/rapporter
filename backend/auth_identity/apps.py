from django.apps import AppConfig


class AuthIdentityConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "auth_identity"

    def ready(self):
        from mailing.service import register_reference_resolver

        from .password_reset import password_reset_path
        from .service import verification_path

        register_reference_resolver("email_identity.verify", verification_path)
        register_reference_resolver("password_reset", password_reset_path)
