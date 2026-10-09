from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from .integration_health import sync_with_health
from .models import Family, FamilyEvent, IntegrationSource, Membership


class FakeResponse:
    def __init__(self, *, data=None, text=""):
        self._data = data
        self.text = text

    def json(self):
        if self._data is None:
            raise ValueError("not json")
        return self._data


def weather_payload(days=7):
    dates = [f"2026-10-{9 + index:02d}" for index in range(days)]
    return {
        "latitude": 49.44,
        "longitude": 7.77,
        "current": {
            "time": "2026-10-09T19:15",
            "temperature_2m": 13.4,
            "apparent_temperature": 12.1,
            "relative_humidity_2m": 74,
            "weather_code": 3,
            "precipitation": 0.0,
            "wind_speed_10m": 8.2,
        },
        "daily": {
            "time": dates,
            "weather_code": [3, 61, 2, 0, 80, 45, 95][:days],
            "temperature_2m_max": [15.2, 14.1, 16.0, 17.4, 12.8, 11.2, 10.5][:days],
            "temperature_2m_min": [8.4, 7.2, 6.8, 7.0, 8.1, 5.4, 4.9][:days],
            "apparent_temperature_max": [14.1, 12.9, 15.0, 16.2, 11.0, 9.8, 8.6][:days],
            "apparent_temperature_min": [7.2, 5.8, 5.9, 6.1, 6.5, 3.9, 3.0][:days],
            "precipitation_probability_max": [20, 65, 15, 5, 80, 30, 70][:days],
            "precipitation_sum": [0.0, 4.2, 0.0, 0.0, 7.1, 0.4, 5.8][:days],
            "wind_speed_10m_max": [18, 21, 14, 11, 24, 13, 32][:days],
            "wind_gusts_10m_max": [31, 38, 26, 20, 44, 28, 58][:days],
            "sunrise": [f"{day}T07:35" for day in dates],
            "sunset": [f"{day}T18:45" for day in dates],
            "uv_index_max": [2.1, 1.8, 2.4, 2.7, 1.2, 1.0, 0.8][:days],
        },
    }


class WeatherIntegrationTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="owner-weather", password="test-pass-123")
        self.family = Family.objects.create(name="Weather Family", slug="weather-family", timezone="Europe/Berlin")
        Membership.objects.create(family=self.family, user=self.user, role=Membership.Role.OWNER)
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def weather_source(self, **config):
        return IntegrationSource.objects.create(
            family=self.family,
            name="7-Tage-Wetter",
            kind=IntegrationSource.Kind.WEATHER,
            config={"adapter": "weather", "latitude": 49.44, "longitude": 7.77, **config},
        )

    @patch("family.weather_integrations._get")
    def test_dwd_jsonp_feed_is_parsed(self, get_mock):
        get_mock.return_value = FakeResponse(
            text=(
                'warnWetter.loadWarnings({"time":1791560000000,"warnings":{"107312000":['
                '{"state":"Rheinland-Pfalz","type":5,"level":2,"start":1791560000000,'
                '"end":1891563600000,"regionName":"Kreisfreie Stadt Kaiserslautern",'
                '"event":"FROST","headline":"Amtliche WARNUNG vor FROST",'
                '"description":"Es tritt Frost auf.","instruction":"Frostschutz beachten."}'
                ']},"vorabInformation":[],"copyright":"Copyright Deutscher Wetterdienst"});'
            )
        )
        source = IntegrationSource.objects.create(
            family=self.family,
            name="DWD Wetterwarnungen",
            kind=IntegrationSource.Kind.WARNING,
            config={"adapter": "dwd", "region": "Kaiserslautern"},
        )
        synced = sync_with_health(source, force=True)
        self.assertEqual(synced, 1)
        warning = FamilyEvent.objects.get(source=source, type="weather.warning")
        self.assertEqual(warning.payload["provider"], "DWD")
        self.assertIn("FROST", warning.title)
        source.refresh_from_db()
        self.assertEqual(source.last_sync_status, "success")

    @patch("family.weather_integrations._get")
    def test_weather_sync_stores_full_seven_day_contract(self, get_mock):
        get_mock.return_value = FakeResponse(data=weather_payload())
        source = self.weather_source(location_label="Kaiserslautern")
        synced = sync_with_health(source, force=True)
        self.assertEqual(synced, 8)
        current = FamilyEvent.objects.get(source=source, external_id="weather:current")
        self.assertEqual(current.type, "weather.current")
        self.assertEqual(current.payload["temperature"], 13.4)
        self.assertEqual(FamilyEvent.objects.filter(source=source, type="weather.forecast").count(), 7)
        requested = get_mock.call_args.kwargs["params"]
        self.assertEqual(requested["forecast_days"], 7)
        self.assertEqual(requested["timezone"], "Europe/Berlin")
        self.assertIn("apparent_temperature_max", requested["daily"])
        self.assertIn("wind_gusts_10m_max", requested["daily"])
        self.assertIn("sunrise", requested["daily"])
        self.assertIn("uv_index_max", requested["daily"])

        response = self.client.get(f"/api/weather/?family={self.family.id}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["source"]["provider"], "Open-Meteo")
        self.assertEqual(response.data["source"]["location"]["label"], "Kaiserslautern")
        self.assertEqual(response.data["current"]["temperature"], 13.4)
        self.assertEqual(len(response.data["days"]), 7)
        first = response.data["days"][0]
        self.assertEqual(first["date"], "2026-10-09")
        self.assertEqual(first["apparent_temp_max"], 14.1)
        self.assertEqual(first["precipitation_probability"], 20)
        self.assertEqual(first["precipitation_sum"], 0.0)
        self.assertEqual(first["wind_gust_max"], 31)
        self.assertEqual(first["uv_index_max"], 2.1)

    @patch("family.weather_integrations._get")
    def test_family_timezone_and_missing_daily_values_are_safe(self, get_mock):
        self.family.timezone = "Pacific/Kiritimati"
        self.family.save(update_fields=["timezone", "updated_at"])
        payload = weather_payload(days=2)
        payload["daily"].pop("wind_gusts_10m_max")
        payload["daily"]["sunrise"] = []
        get_mock.return_value = FakeResponse(data=payload)
        source = self.weather_source()
        sync_with_health(source, force=True)
        event = FamilyEvent.objects.get(source=source, external_id="weather:2026-10-09")
        self.assertEqual(event.starts_at.astimezone().date().isoformat()[:4], "2026")
        response = self.client.get(f"/api/weather/?family={self.family.id}")
        self.assertEqual(response.data["days"][0]["date"], "2026-10-09")
        self.assertIsNone(response.data["days"][0]["wind_gust_max"])
        self.assertIsNone(response.data["days"][0]["sunrise"])
        self.assertEqual(get_mock.call_args.kwargs["params"]["timezone"], "Pacific/Kiritimati")

    @patch("family.weather_integrations._get")
    def test_stale_weather_stays_available_after_failed_refresh(self, get_mock):
        get_mock.return_value = FakeResponse(data=weather_payload())
        source = self.weather_source()
        sync_with_health(source, force=True)
        source.refresh_from_db()
        source.last_sync_status = "error"
        source.last_sync_error = "provider timeout"
        source.last_attempt_at = timezone.now()
        source.save(update_fields=["last_sync_status", "last_sync_error", "last_attempt_at", "updated_at"])
        response = self.client.get(f"/api/weather/?family={self.family.id}")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["source"]["stale"])
        self.assertEqual(response.data["source"]["last_sync_error"], "provider timeout")
        self.assertEqual(response.data["current"]["temperature"], 13.4)
        self.assertEqual(len(response.data["days"]), 7)

    def test_weather_data_is_not_a_calendar_event_and_alerts_are_separate(self):
        source = self.weather_source()
        current = FamilyEvent.objects.create(
            family=self.family, source=source, external_id="weather:current", type="weather.current",
            title="12 °C", starts_at=timezone.now() - timedelta(minutes=5),
            payload={"provider": "Open-Meteo", "temperature": 12, "weather_code": 2},
        )
        forecast = FamilyEvent.objects.create(
            family=self.family, source=source, external_id="weather:tomorrow", type="weather.forecast",
            title="Wetter morgen", starts_at=timezone.now() + timedelta(days=1), payload={"date": "2026-10-10", "temp_min": 7, "temp_max": 14},
        )
        warning_source = IntegrationSource.objects.create(family=self.family, name="DWD", kind=IntegrationSource.Kind.WARNING, config={"adapter": "dwd"})
        warning = FamilyEvent.objects.create(
            family=self.family, source=warning_source, external_id="dwd:test", type="weather.warning", title="Sturmwarnung",
            starts_at=timezone.now() - timedelta(minutes=10), ends_at=timezone.now() + timedelta(hours=3), payload={"provider": "DWD", "level": 3, "region": "Kaiserslautern"},
        )
        dashboard = self.client.get(f"/api/dashboard/?family={self.family.id}")
        self.assertEqual(dashboard.status_code, 200)
        dashboard_ids = {item["id"] for item in dashboard.data["events"]}
        self.assertNotIn(str(current.id), dashboard_ids)
        self.assertNotIn(str(forecast.id), dashboard_ids)
        self.assertIn(str(warning.id), dashboard_ids)
        self.assertEqual(dashboard.data["weather"]["current"]["temperature"], 12)
        events = self.client.get("/api/events/")
        event_ids = {item["id"] for item in events.data}
        self.assertNotIn(str(current.id), event_ids)
        self.assertNotIn(str(forecast.id), event_ids)
        self.assertIn(str(warning.id), event_ids)
        weather = self.client.get(f"/api/weather/?family={self.family.id}")
        self.assertEqual([item["title"] for item in weather.data["alerts"]], ["Sturmwarnung"])

    def test_foreign_family_weather_is_forbidden(self):
        other = Family.objects.create(name="Other Family", slug="other-weather-family")
        source = IntegrationSource.objects.create(family=other, name="Other weather", kind=IntegrationSource.Kind.WEATHER, config={"adapter": "weather"})
        FamilyEvent.objects.create(family=other, source=source, external_id="weather:current", type="weather.current", title="99 °C", starts_at=timezone.now(), payload={"temperature": 99})
        response = self.client.get(f"/api/weather/?family={other.id}")
        self.assertEqual(response.status_code, 403)
