from django.apps import AppConfig


class ExpensesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "expenses"

    def ready(self):
        # Register the Expense-side consumer lazily at app startup so the generic
        # document core never imports a domain model directly.
        from . import document_consumer  # noqa: F401
