from unittest.mock import MagicMock, patch
from urllib.parse import parse_qs

from django.test import SimpleTestCase, override_settings

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
