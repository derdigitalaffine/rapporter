from http.cookies import SimpleCookie
from uuid import UUID

from asgiref.sync import async_to_sync
from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from channels.layers import get_channel_layer
from django.contrib.auth.models import AnonymousUser
from rest_framework_simplejwt.authentication import JWTAuthentication

from auth_sessions.cookies import ACCESS_COOKIE
from auth_sessions.models import AuthSession
from auth_sessions.service import active_session_for_token


def family_group(family_id):
    return f"family.sync.{family_id}"


@database_sync_to_async
def user_from_cookie(raw_cookie):
    try:
        cookie = SimpleCookie()
        cookie.load(raw_cookie or "")
        value = cookie.get(ACCESS_COOKIE)
        if value is None:
            return AnonymousUser()
        auth = JWTAuthentication()
        token = auth.get_validated_token(value.value)
        user = auth.get_user(token)
        session = active_session_for_token(token)
        if session.surface != AuthSession.Surface.APP:
            return AnonymousUser()
        return user
    except Exception:
        return AnonymousUser()


@database_sync_to_async
def may_access_family(user, family_id):
    if not getattr(user, "is_authenticated", False):
        return False
    from .models import Family, Membership
    try:
        UUID(str(family_id))
    except (TypeError, ValueError):
        return False
    return Membership.objects.filter(
        user_id=user.pk,
        family_id=family_id,
        family__status=Family.Status.ACTIVE,
    ).exists()


class CookieJWTWebSocketMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        headers = dict(scope.get("headers", []))
        scope = dict(scope)
        scope["sync_cookie"] = headers.get(b"cookie", b"").decode("latin1")
        scope["user"] = await user_from_cookie(scope["sync_cookie"])
        return await self.app(scope, receive, send)


class SyncWakeConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        self.family_id = str(self.scope["url_route"]["kwargs"]["family_id"])
        if not await may_access_family(self.scope.get("user"), self.family_id):
            await self.close(code=4403)
            return
        self.group_name = family_group(self.family_id)
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, code):
        if getattr(self, "group_name", None):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive_json(self, content, **kwargs):
        # WebSocket is wake-up only; clients cannot write or request domain data here.
        if content not in ({"type": "ping"}, {"type": "ping", "protocol_version": 1}):
            await self.close(code=4400)

    async def sync_available(self, event):
        user = await user_from_cookie(self.scope["sync_cookie"]) if "sync_cookie" in self.scope else self.scope.get("user")
        if not await may_access_family(user, self.family_id):
            await self.close(code=4403)
            return
        await self.send_json({
            "type": "sync_available",
            "family_id": self.family_id,
            "cursor": int(event["cursor"]),
        })


def publish(family_id, cursor):
    layer = get_channel_layer()
    if layer is None:
        return
    try:
        async_to_sync(layer.group_send)(
            family_group(str(family_id)),
            {"type": "sync_available", "cursor": int(cursor)},
        )
    except Exception:
        # Live wake-up is never a correctness dependency. HTTP sync triggers remain authoritative.
        return
