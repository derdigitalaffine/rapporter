from django.apps import AppConfig


class AuthRecoveryConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "auth_recovery"

    def ready(self):
        from mailing.service import register_reference_resolver

        from .service import password_reset_path, security_center_path

        register_reference_resolver("auth_recovery.reset", password_reset_path)
        register_reference_resolver("auth_recovery.security_center", security_center_path)
