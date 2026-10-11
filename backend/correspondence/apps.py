from django.apps import AppConfig


class CorrespondenceConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "correspondence"

    def ready(self):
        from .context import register_context_adapters

        register_context_adapters()
