import os
from unittest import skipUnless

from asgiref.sync import async_to_sync, sync_to_async
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
            await sync_to_async(publish)(str(self.family.id), 42)
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

    @override_settings(CHANNEL_LAYERS={"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}})
    def test_membership_revocation_closes_before_next_wakeup(self):
        async def scenario():
            communicator = WebsocketCommunicator(self.app_for(self.user), f"/ws/sync/{self.family.id}/")
            connected, _ = await communicator.connect()
            self.assertTrue(connected)
            await sync_to_async(Membership.objects.filter(user=self.user, family=self.family).delete)()
            await sync_to_async(publish)(str(self.family.id), 99)
            output = await communicator.receive_output(timeout=1)
            self.assertEqual(output["type"], "websocket.close")
            self.assertEqual(output["code"], 4403)
            await communicator.disconnect()
        async_to_sync(scenario)()


@skipUnless(os.environ.get("OFFLINE_LIVE_TEST_REDIS") == "1", "Requires dedicated CI Redis service")
@override_settings(CHANNEL_LAYERS={"default": {"BACKEND": "channels_redis.core.RedisChannelLayer", "CONFIG": {"hosts": ["redis://127.0.0.1:6379/15"]}}})
class RedisOfflineLiveTests(TransactionTestCase):
    setUp = OfflineLiveTests.setUp
    app_for = OfflineLiveTests.app_for

    def test_real_redis_transport_delivers_cursor_without_domain_data(self):
        async def scenario():
            communicator = WebsocketCommunicator(self.app_for(self.user), f"/ws/sync/{self.family.id}/")
            connected, _ = await communicator.connect()
            self.assertTrue(connected)
            await sync_to_async(publish)(str(self.family.id), 123)
            self.assertEqual(await communicator.receive_json_from(timeout=3), {
                "type": "sync_available", "family_id": str(self.family.id), "cursor": 123,
            })
            await communicator.disconnect()
        async_to_sync(scenario)()
