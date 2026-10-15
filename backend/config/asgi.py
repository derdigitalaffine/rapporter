import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

from django.core.asgi import get_asgi_application

django_asgi_app = get_asgi_application()

from channels.routing import ProtocolTypeRouter, URLRouter
from channels.security.websocket import AllowedHostsOriginValidator
from django.urls import path

from family.sync_live import CookieJWTWebSocketMiddleware, SyncWakeConsumer

application = ProtocolTypeRouter({
    "http": django_asgi_app,
    "websocket": AllowedHostsOriginValidator(
        CookieJWTWebSocketMiddleware(
            URLRouter([
                path("ws/sync/<uuid:family_id>/", SyncWakeConsumer.as_asgi()),
            ])
        )
    ),
})
