from django.apps import AppConfig


class BabyConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "baby"

    def ready(self):
        # Kept in a separate module so the large domain model file remains
        # readable; importing here registers it with Django's app registry.
        from . import media_models  # noqa: F401
