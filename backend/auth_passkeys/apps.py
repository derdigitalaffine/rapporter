from django.apps import AppConfig


class AuthPasskeysConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "auth_passkeys"

    def ready(self):
        from . import checks  # noqa: F401
