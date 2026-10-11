from django.apps import AppConfig


class WishlistsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "wishlists"

    def ready(self):
        from .context import register_context_adapters

        register_context_adapters()
