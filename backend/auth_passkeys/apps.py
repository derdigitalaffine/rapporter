from django.apps import AppConfig


class AuthPasskeysConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "auth_passkeys"

    def ready(self):
        from mailing.service import register_reference_resolver

        from . import checks  # noqa: F401
        from .mailing import passkey_security_path

        register_reference_resolver("passkey.security", passkey_security_path)
