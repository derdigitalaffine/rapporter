import json
from unittest.mock import Mock, patch

import requests
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from .models import Family, Membership, ShoppingList
from .shopping_models import ShoppingListStoreProfile, ShoppingStore


@override_settings(
    NOMINATIM_BASE_URL="https://nominatim.example",
    NOMINATIM_RATE_LIMIT_ENABLED=False,
    SHOPPING_STORE_AUTOCOMPLETE_ENABLED=True,
    NOMINATIM_TIMEOUT=3,
    NOMINATIM_USER_AGENT="FamilyOS test geocoder",
    NOMINATIM_CACHE_SECONDS=900,
)
class ShoppingStoreLocationTests(TestCase):
    def setUp(self):
        cache.clear()
        User = get_user_model()
        self.user = User.objects.create_user(username="location-owner", password="x")
        self.outsider = User.objects.create_user(username="location-outsider", password="x")
        self.family = Family.objects.create(name="Location Family", slug="location-family")
        self.other_family = Family.objects.create(name="Other Location Family", slug="other-location-family")
        Membership.objects.create(family=self.family, user=self.user, role=Membership.Role.OWNER)
        Membership.objects.create(family=self.other_family, user=self.outsider, role=Membership.Role.OWNER)
        self.shopping_list = ShoppingList.objects.create(family=self.family, name="Groceries")
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def _response(self, payload, status_code=200, headers=None):
        response = Mock()
        response.status_code = status_code
        response.headers = headers or {}
        response.is_redirect = 300 <= status_code < 400
        response.is_permanent_redirect = status_code in {301, 308}
        encoded = json.dumps(payload).encode("utf-8")
        response.iter_content.return_value = [encoded]
        return response

    def _provider_row(self):
        return {
            "place_id": 12345,
            "lat": "49.443100",
            "lon": "7.768900",
            "display_name": "Markt, Marktstraße 1, Kaiserslautern, Deutschland",
            "namedetails": {"name": "Markt"},
            "address": {"shop": "Markt", "city": "Kaiserslautern"},
        }

    @patch("family.shopping_geocoder.requests.get")
    def test_explicit_search_uses_fixed_provider_without_redirects_and_caches(self, get):
        get.return_value = self._response([self._provider_row()])
        url = f"/api/shopping-store-locations/?family={self.family.id}&mode=search&q=Markt"

        first = self.client.get(url)
        second = self.client.get(url)

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(get.call_count, 1)
        args, kwargs = get.call_args
        self.assertEqual(args[0], "https://nominatim.example/search")
        self.assertFalse(kwargs["allow_redirects"])
        self.assertTrue(kwargs["stream"])
        self.assertEqual(kwargs["timeout"], 3.0)
        self.assertEqual(kwargs["headers"]["User-Agent"], "FamilyOS test geocoder")
        self.assertEqual(kwargs["params"]["limit"], 5)
        self.assertNotIn("family", kwargs["params"])
        result = first.data["results"][0]
        self.assertEqual(result["provider"], "nominatim")
        self.assertEqual(result["provider_ref"], "12345")
        self.assertEqual(result["name"], "Markt")
        self.assertEqual(result["latitude"], "49.443100")
        self.assertEqual(first.data["attribution"], "© OpenStreetMap contributors")

    @patch("family.shopping_geocoder.requests.get")
    def test_reverse_lookup_only_for_explicit_coordinates(self, get):
        get.return_value = self._response(self._provider_row())
        response = self.client.get(
            f"/api/shopping-store-locations/?family={self.family.id}&mode=reverse&lat=49.4431&lon=7.7689"
        )
        self.assertEqual(response.status_code, 200)
        args, kwargs = get.call_args
        self.assertEqual(args[0], "https://nominatim.example/reverse")
        self.assertEqual(kwargs["params"]["lat"], "49.443100")
        self.assertEqual(kwargs["params"]["lon"], "7.768900")

    @patch("family.shopping_geocoder.requests.get")
    def test_provider_failure_is_bounded(self, get):
        get.side_effect = requests.Timeout("slow")
        response = self.client.get(
            f"/api/shopping-store-locations/?family={self.family.id}&mode=search&q=Markt"
        )
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.data["code"], "store_lookup_unavailable")

    @patch("family.shopping_geocoder.requests.get")
    def test_redirect_is_not_followed(self, get):
        get.return_value = self._response({}, status_code=302)
        response = self.client.get(
            f"/api/shopping-store-locations/?family={self.family.id}&mode=search&q=Markt"
        )
        self.assertEqual(response.status_code, 503)
        self.assertFalse(get.call_args.kwargs["allow_redirects"])

    @patch("family.shopping_geocoder.requests.get")
    def test_oversized_stream_is_rejected_even_without_content_length(self, get):
        response = self._response([])
        response.iter_content.return_value = [b"x" * 300_000, b"y" * 300_000]
        get.return_value = response
        result = self.client.get(
            f"/api/shopping-store-locations/?family={self.family.id}&mode=search&q=Markt"
        )
        self.assertEqual(result.status_code, 503)
        self.assertEqual(result.data["code"], "store_lookup_unavailable")
        response.close.assert_called_once()

    @patch("family.shopping_geocoder.requests.get")
    def test_lookup_rejects_cross_family_tenant_before_upstream(self, get):
        response = self.client.get(
            f"/api/shopping-store-locations/?family={self.other_family.id}&mode=search&q=Markt"
        )
        self.assertEqual(response.status_code, 404)
        get.assert_not_called()

    def test_resolve_is_idempotent_and_assigns_canonical_store(self):
        payload = {
            "family": str(self.family.id),
            "shopping_list": str(self.shopping_list.id),
            "provider": "nominatim",
            "provider_ref": "12345",
            "name": "Markt",
            "branch_label": "Kaiserslautern",
            "address": "Markt, Marktstraße 1, Kaiserslautern, Deutschland",
            "latitude": "49.443100",
            "longitude": "7.768900",
        }
        first = self.client.post("/api/shopping-store-locations/resolve/", payload, format="json")
        second = self.client.post("/api/shopping-store-locations/resolve/", payload, format="json")

        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 200)
        self.assertTrue(first.data["created"])
        self.assertFalse(second.data["created"])
        self.assertEqual(ShoppingStore.objects.filter(family=self.family).count(), 1)
        store = ShoppingStore.objects.get(family=self.family)
        self.assertEqual(store.location_provider, "nominatim")
        self.assertEqual(store.location_ref, "12345")
        assignment = ShoppingListStoreProfile.objects.get(shopping_list=self.shopping_list)
        self.assertEqual(assignment.store_id, store.id)
        self.shopping_list.refresh_from_db()
        self.assertEqual(self.shopping_list.store, "Markt · Kaiserslautern")

    def test_resolve_rejects_cross_family_list(self):
        other_list = ShoppingList.objects.create(family=self.other_family, name="Other")
        response = self.client.post(
            "/api/shopping-store-locations/resolve/",
            {
                "family": str(self.family.id),
                "shopping_list": str(other_list.id),
                "provider": "nominatim",
                "provider_ref": "12345",
                "name": "Markt",
                "latitude": "49.443100",
                "longitude": "7.768900",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(ShoppingStore.objects.count(), 0)
