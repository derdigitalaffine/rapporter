from django.apps import AppConfig


class GamesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "games"

    def ready(self):
        # Feature models are imported explicitly so Django registers them without
        # bloating the core game model module.
        from . import category_models  # noqa: F401
