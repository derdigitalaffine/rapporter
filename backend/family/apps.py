from django.apps import AppConfig


class FamilyConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "family"

    def ready(self):
        from . import models_features  # noqa: F401
        from . import prediction_signals  # noqa: F401
        from . import signals  # noqa: F401
