from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from .matomo import (
    MatomoError,
    _bounded_metrics,
    _bounded_rows,
    _bounded_series,
    _validated_api_url,
    get_matomo_config,
)


class SuperadminMatomoTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.admin = User.objects.create_superuser(username="root", email="root@example.test", password="pass")
        self.regular = User.objects.create_user(username="regular", email="regular@example.test", password="pass")

    def test_regular_user_cannot_read_matomo_status_or_report(self):
        client = APIClient();client.force_authenticate(self.regular)
        self.assertEqual(client.get("/api/superadmin/analytics/matomo/status/").status_code, 403)
        self.assertEqual(client.get("/api/superadmin/analytics/matomo/report/").status_code, 403)

    @override_settings(MATOMO_BASE_URL="", MATOMO_SITE_ID="", MATOMO_AUTH_TOKEN="")
    def test_disabled_configuration_is_safe_and_does_not_expose_token(self):
        client = APIClient();client.force_authenticate(self.admin)
        status_response = client.get("/api/superadmin/analytics/matomo/status/")
        self.assertEqual(status_response.status_code, 200)
        self.assertFalse(status_response.data["configured"])
        self.assertFalse(status_response.data["auth_token_configured"])
        self.assertNotIn("auth_token", status_response.data)
        self.assertNotIn("base_url", status_response.data)

        report_response = client.get("/api/superadmin/analytics/matomo/report/")
        self.assertEqual(report_response.status_code, 503)
        self.assertFalse(report_response.data["configured"])

    @override_settings(
        MATOMO_BASE_URL="https://analytics.example.test",
        MATOMO_SITE_ID="7",
        MATOMO_AUTH_TOKEN="top-secret-token",
    )
    @patch("family.superadmin_analytics_views.reporting_snapshot")
    def test_report_returns_only_aggregated_snapshot(self, reporting_snapshot):
        reporting_snapshot.return_value = {
            "summary": {"nb_visits": 12, "nb_uniq_visitors": 8, "nb_actions": 44},
            "series": {"2026-10-10": {"nb_visits": 4}},
            "top_pages": [{"label": "/today", "nb_visits": 4}],
            "referrers": [{"label": "Direct Entry", "nb_visits": 3}],
            "events": [{"label": "tasks", "nb_events": 5}],
        }
        client = APIClient();client.force_authenticate(self.admin)
        response = client.get("/api/superadmin/analytics/matomo/report/?days=7")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertTrue(response.data["configured"])
        self.assertEqual(response.data["site_id"], "7")
        self.assertEqual(response.data["days"], 7)
        self.assertNotIn("auth_token", response.data)
        self.assertNotIn("top-secret-token", str(response.data))
        self.assertEqual(response.data["summary"]["nb_visits"], 12)
        reporting_snapshot.assert_called_once()
        date_range = reporting_snapshot.call_args.kwargs["date_range"]
        self.assertEqual(len(date_range.split(",")), 2)

    @override_settings(
        MATOMO_BASE_URL="https://analytics.example.test",
        MATOMO_SITE_ID="7",
        MATOMO_AUTH_TOKEN="top-secret-token",
    )
    def test_report_rejects_unbounded_window(self):
        client = APIClient();client.force_authenticate(self.admin)
        response = client.get("/api/superadmin/analytics/matomo/report/?days=3650")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["allowed_days"], [7, 30, 90])

    @override_settings(
        MATOMO_BASE_URL="http://analytics.example.test",
        MATOMO_SITE_ID="7",
        MATOMO_AUTH_TOKEN="secret",
    )
    def test_reporting_url_requires_https(self):
        with self.assertRaises(MatomoError):
            _validated_api_url(get_matomo_config())

    def test_page_rows_strip_query_fragment_and_unknown_fields(self):
        rows = _bounded_rows([
            {
                "label": "/documents/42?token=sensitive#section",
                "nb_visits": 5,
                "nb_hits": 8,
                "bounce_rate": "10%",
                "avg_time_on_page": 12,
                "visitor_id": "must-not-leak",
            }
        ], kind="page")
        self.assertEqual(rows[0]["label"], "/documents/42")
        self.assertNotIn("visitor_id", rows[0])
        self.assertNotIn("sensitive", str(rows[0]))

    def test_summary_metrics_drop_unknown_matomo_fields(self):
        bounded = _bounded_metrics(
            {
                "nb_visits": 5,
                "nb_actions": 9,
                "nb_uniq_visitors": 3,
                "visitor_id": "must-not-leak",
                "custom_dimension_1": "private",
            },
            fields=("nb_visits", "nb_actions", "nb_uniq_visitors"),
        )
        self.assertEqual(bounded, {"nb_visits": 5, "nb_actions": 9, "nb_uniq_visitors": 3})
        self.assertNotIn("visitor_id", bounded)
        self.assertNotIn("private", str(bounded))

    def test_series_drops_unknown_dates_and_fields(self):
        bounded = _bounded_series(
            {
                "2026-10-10": {"nb_visits": 4, "nb_actions": 8, "visitor_id": "secret"},
                "totals": {"nb_visits": 99, "visitor_id": "secret"},
            }
        )
        self.assertEqual(bounded, {"2026-10-10": {"nb_visits": 4, "nb_actions": 8}})
        self.assertNotIn("secret", str(bounded))
