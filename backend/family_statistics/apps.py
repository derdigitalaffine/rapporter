from django.apps import AppConfig


class FamilyStatisticsConfig(AppConfig):
    name = "family_statistics"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        from . import signals  # noqa: F401
