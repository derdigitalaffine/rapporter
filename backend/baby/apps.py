from django.apps import AppConfig


class BabyConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "baby"

    def ready(self):
        # Kept in separate modules so the large domain model file remains
        # readable; importing here registers the models and cleanup signals.
        from . import media_models  # noqa: F401
        from . import media_signals  # noqa: F401
        from . import reference_models  # noqa: F401
