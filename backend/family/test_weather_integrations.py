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


class WeatherIntegrationTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="owner-weather", password="test-pass-123")
        self.family = Family.objects.create(name="Weather Family", slug="weather-family", timezone="Europe/Berlin")
        Membership.objects.create(family=self.family, user=self.user, role=Membership.Role.OWNER)
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    @patch("family.weather_integrations._get")
    def test_dwd_jsonp_feed_is_parsed(self, get_mock):
        get_mock.return_value = FakeResponse(
            text=(
                'warnWetter.loadWarnings({"time":1791560000000,"warnings":{"107312000":['
                '{"state":"Rheinland-Pfalz","type":5,"level":2,"start":1791560000000,'
                '"end":1791563600000,"regionName":"Kreisfreie Stadt Kaiserslautern",'
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
    def test_weather_sync_stores_current_conditions_and_forecast(self, get_mock):
        get_mock.return_value = FakeResponse(data={
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
                "time": ["2026-10-09", "2026-10-10"],
                "weather_code": [3, 61],
                "temperature_2m_max": [15.2, 14.1],
                "temperature_2m_min": [8.4, 7.2],
                "precipitation_probability_max": [20, 65],
                "wind_speed_10m_max": [18.0, 21.0],
            },
        })
        source = IntegrationSource.objects.create(
            family=self.family,
            name="7-Tage-Wetter",
            kind=IntegrationSource.Kind.WEATHER,
            config={"adapter": "weather", "latitude": 49.44, "longitude": 7.77},
        )

        synced = sync_with_health(source, force=True)

        self.assertEqual(synced, 3)
        current = FamilyEvent.objects.get(source=source, external_id="weather:current")
        self.assertEqual(current.type, "weather.current")
        self.assertEqual(current.title, "13.4 °C")
        self.assertEqual(current.payload["temperature"], 13.4)
        self.assertEqual(current.payload["apparent_temperature"], 12.1)
        self.assertEqual(current.payload["humidity"], 74)
        self.assertEqual(current.payload["weather_code"], 3)
        requested_params = get_mock.call_args.kwargs["params"]
        self.assertIn("temperature_2m", requested_params["current"])
        self.assertIn("weather_code", requested_params["current"])
        self.assertEqual(FamilyEvent.objects.filter(source=source, type="weather.forecast").count(), 2)

    def test_dashboard_keeps_recent_current_weather_visible(self):
        source = IntegrationSource.objects.create(
            family=self.family,
            name="7-Tage-Wetter",
            kind=IntegrationSource.Kind.WEATHER,
            config={"adapter": "weather"},
        )
        current = FamilyEvent.objects.create(
            family=self.family,
            source=source,
            external_id="weather:current",
            type="weather.current",
            title="12 °C",
            starts_at=timezone.now() - timedelta(minutes=5),
            payload={"provider": "Open-Meteo", "temperature": 12, "weather_code": 2},
        )

        response = self.client.get(f"/api/dashboard/?family={self.family.id}")

        self.assertEqual(response.status_code, 200)
        ids = [item["id"] for item in response.data["events"]]
        self.assertIn(str(current.id), ids)
