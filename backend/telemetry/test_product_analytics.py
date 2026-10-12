from unittest.mock import MagicMock, patch
from urllib.parse import parse_qs

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase, override_settings
from rest_framework.test import APIClient

from family.models import Family, Membership

from .matomo_product import (
    ProductAnalyticsError,
    ProductAnalyticsSchemaError,
    dispatch_product_event,
    validate_product_event,
)


PAGEVIEW = {
    "kind": "pageview",
    "feature": "documents",
    "action": "open",
    "result": "success",
    "route_family": "documents",
    "duration_bucket": "none",
}


class ProductAnalyticsContractTests(SimpleTestCase):
    def test_allowlist_rejects_unknown_fields(self):
        with self.assertRaisesRegex(ProductAnalyticsSchemaError, "unknown_field"):
            validate_product_event({**PAGEVIEW, "email": "private@example.com"})

    def test_route_family_cannot_carry_query_or_fragment_data(self):
        for value in ("documents?note=secret", "documents#private", "/documents/42"):
            with self.subTest(value=value):
                with self.assertRaisesRegex(ProductAnalyticsSchemaError, "invalid_route_family"):
                    validate_product_event({**PAGEVIEW, "route_family": value})

    def test_pageview_semantics_are_fixed(self):
        with self.assertRaisesRegex(ProductAnalyticsSchemaError, "invalid_pageview_semantics"):
            validate_product_event({**PAGEVIEW, "action": "search"})

    @override_settings(MATOMO_TRACKING_ENABLED=False)
    @patch("telemetry.matomo_product.urlopen")
    def test_disabled_tracking_never_calls_matomo(self, mocked_urlopen):
        self.assertFalse(dispatch_product_event(PAGEVIEW))
        mocked_urlopen.assert_not_called()

    @override_settings(
        MATOMO_TRACKING_ENABLED=True,
        MATOMO_BASE_URL="https://analytics.example.com",
        MATOMO_SITE_ID="7",
        MATOMO_TRACKING_APP_ORIGIN="https://family.example.com/private/base",
        MATOMO_TRACKING_TIMEOUT=2,
    )
    @patch("telemetry.matomo_product.urlopen")
    def test_pageview_egress_contains_only_normalized_public_metadata(self, mocked_urlopen):
        response = MagicMock()
        response.__enter__.return_value = response
        mocked_urlopen.return_value = response

        self.assertTrue(dispatch_product_event(PAGEVIEW))

        request = mocked_urlopen.call_args.args[0]
        params = parse_qs(request.data.decode("utf-8"))
        self.assertEqual(request.full_url, "https://analytics.example.com/matomo.php")
        self.assertEqual(params["idsite"], ["7"])
        self.assertEqual(params["url"], ["https://family.example.com/analytics/documents"])
        self.assertEqual(params["action_name"], ["FamilyOS/documents"])
        self.assertNotIn("e_c", params)
        for forbidden in ("uid", "cid", "_id", "cip", "urlref", "token_auth"):
            self.assertNotIn(forbidden, params)

    @override_settings(
        MATOMO_TRACKING_ENABLED=True,
        MATOMO_BASE_URL="https://analytics.example.com",
        MATOMO_SITE_ID="7",
        MATOMO_TRACKING_APP_ORIGIN="https://family.example.com",
        MATOMO_TRACKING_TIMEOUT=2,
    )
    @patch("telemetry.matomo_product.urlopen")
    def test_event_egress_uses_only_versioned_taxonomy(self, mocked_urlopen):
        response = MagicMock()
        response.__enter__.return_value = response
        mocked_urlopen.return_value = response

        event = {
            "kind": "event",
            "feature": "tasks",
            "action": "complete",
            "result": "success",
            "route_family": "todo",
            "duration_bucket": "100_500ms",
        }
        self.assertTrue(dispatch_product_event(event))

        request = mocked_urlopen.call_args.args[0]
        params = parse_qs(request.data.decode("utf-8"))
        self.assertEqual(params["e_c"], ["familyos.tasks"])
        self.assertEqual(params["e_a"], ["complete"])
        self.assertEqual(params["e_n"], ["success:100_500ms"])
        self.assertEqual(params["url"], ["https://family.example.com/analytics/todo"])

    @override_settings(
        MATOMO_TRACKING_ENABLED=True,
        MATOMO_BASE_URL="http://analytics.example.com",
        MATOMO_SITE_ID="7",
        MATOMO_TRACKING_APP_ORIGIN="https://family.example.com",
    )
    def test_tracking_target_must_use_https(self):
        with self.assertRaises(ProductAnalyticsError):
            dispatch_product_event(PAGEVIEW)


class ProductAnalyticsEndpointTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="product-member")
        self.family = Family.objects.create(name="Product family", slug="product-family")
        Membership.objects.create(user=self.user, family=self.family, role=Membership.Role.ADULT)
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    @patch("telemetry.product_analytics_views.dispatch_product_event")
    def test_anonymous_requests_do_not_dispatch(self, dispatch):
        self.client.force_authenticate(None)
        response = self.client.post("/api/analytics/product-event/", PAGEVIEW, format="json")
        self.assertIn(response.status_code, (401, 403))
        dispatch.assert_not_called()

    @patch("telemetry.product_analytics_views.dispatch_product_event")
    def test_foreign_family_requests_do_not_dispatch(self, dispatch):
        other = Family.objects.create(name="Other family", slug="other-product-family")
        response = self.client.post(f"/api/analytics/product-event/?family={other.pk}", PAGEVIEW, format="json")
        self.assertEqual(response.status_code, 403)
        dispatch.assert_not_called()

    @patch("telemetry.product_analytics_views.dispatch_product_event")
    def test_suspended_membership_does_not_dispatch(self, dispatch):
        self.family.status = Family.Status.SUSPENDED
        self.family.save(update_fields=["status"])
        response = self.client.post("/api/analytics/product-event/", PAGEVIEW, format="json")
        self.assertEqual(response.status_code, 403)
        dispatch.assert_not_called()

    @override_settings(MATOMO_TRACKING_ENABLED=False)
    @patch("telemetry.matomo_product.urlopen")
    def test_disabled_endpoint_has_no_egress(self, urlopen):
        response = self.client.post("/api/analytics/product-event/", PAGEVIEW, format="json")
        self.assertEqual(response.status_code, 204)
        urlopen.assert_not_called()

    @patch("telemetry.matomo_product.urlopen")
    def test_private_payload_is_rejected_before_egress(self, urlopen):
        response = self.client.post("/api/analytics/product-event/", {**PAGEVIEW, "email": "private@example.test"}, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data, {"code": "unknown_field"})
        urlopen.assert_not_called()

    @patch("telemetry.product_analytics_views.dispatch_product_event", side_effect=ProductAnalyticsError("vendor private configuration"))
    def test_outage_is_sanitized_and_does_not_fail_the_product(self, dispatch):
        with self.assertLogs("telemetry", level="WARNING") as logs:
            response = self.client.post("/api/analytics/product-event/", PAGEVIEW, format="json")
        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.data, {"accepted": False})
        self.assertNotIn("vendor private", str(response.data))
        self.assertNotIn("vendor private", " ".join(logs.output))
