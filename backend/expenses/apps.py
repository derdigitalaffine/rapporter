from django.apps import AppConfig


class ExpensesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "expenses"

    def import_models(self):
        super().import_models()
        # Finance extension models live in dedicated modules to keep the
        # canonical expense model file stable while still participating in
        # Django model discovery and migration checks.
        from . import commitment_models  # noqa: F401
        from . import period_models  # noqa: F401
        from . import participant_models  # noqa: F401

    def ready(self):
        from documents.consumers import register_processing_consumer
        from .context import register_expense_context_adapters
        from .document_receipts import consume_receipt_processing_run
        from . import commitment_signals  # noqa: F401

        register_processing_consumer("expense", "receipt", consume_receipt_processing_run)
        register_expense_context_adapters()
