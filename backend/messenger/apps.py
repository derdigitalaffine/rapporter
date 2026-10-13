from django.apps import AppConfig


class MessengerConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "messenger"

    def ready(self):
        from mailing.service import register_reference_resolver
        from .invitations import invitation_path
        from . import signals  # noqa: F401
        register_reference_resolver("chat.invitation", invitation_path)
