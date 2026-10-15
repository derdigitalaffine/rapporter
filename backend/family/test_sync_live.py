from asgiref.sync import async_to_sync
from channels.routing import URLRouter
from channels.testing import WebsocketCommunicator
from django.contrib.auth import get_user_model
from django.test import TransactionTestCase, override_settings
from django.urls import path

from .models import Family, Membership
from .sync_live import SyncWakeConsumer, publish


class OfflineLiveTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        self.user = get_user_model().objects.create_user(username="live-owner", password="x")
        self.family = Family.objects.create(name="Live family", slug="live-family")
        Membership.objects.create(family=self.family, user=self.user, role=Membership.Role.OWNER)

    def app_for(self, user):
        router = URLRouter([path("ws/sync/<uuid:family_id>/", SyncWakeConsumer.as_asgi())])

        async def app(scope, receive, send):
            scope = dict(scope)
            scope["user"] = user
            await router(scope, receive, send)

        return app

    @override_settings(CHANNEL_LAYERS={"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}})
    def test_member_receives_cursor_only_wakeup(self):
        async def scenario():
            communicator = WebsocketCommunicator(self.app_for(self.user), f"/ws/sync/{self.family.id}/")
            connected, _ = await communicator.connect()
            self.assertTrue(connected)
            publish(str(self.family.id), 42)
            message = await communicator.receive_json_from(timeout=1)
            self.assertEqual(message, {
                "type": "sync_available",
                "family_id": str(self.family.id),
                "cursor": 42,
            })
            await communicator.disconnect()

        async_to_sync(scenario)()

    @override_settings(CHANNEL_LAYERS={"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}})
    def test_non_member_is_rejected(self):
        stranger = get_user_model().objects.create_user(username="stranger", password="x")

        async def scenario():
            communicator = WebsocketCommunicator(self.app_for(stranger), f"/ws/sync/{self.family.id}/")
            connected, code = await communicator.connect()
            self.assertFalse(connected)
            self.assertEqual(code, 4403)

        async_to_sync(scenario)()

    @override_settings(CHANNEL_LAYERS={"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}})
    def test_websocket_rejects_domain_payloads(self):
        async def scenario():
            communicator = WebsocketCommunicator(self.app_for(self.user), f"/ws/sync/{self.family.id}/")
            connected, _ = await communicator.connect()
            self.assertTrue(connected)
            await communicator.send_json_to({"type": "update", "entity": {"title": "must not travel here"}})
            close = await communicator.receive_output(timeout=1)
            self.assertEqual(close["type"], "websocket.close")
            self.assertEqual(close["code"], 4400)

        async_to_sync(scenario)()
