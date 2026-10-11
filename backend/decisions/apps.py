from django.apps import AppConfig


class DecisionsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "decisions"

    def ready(self):
        from family.context_links import default_context_registry
        from .context import register_decision_context

        register_decision_context(default_context_registry())
