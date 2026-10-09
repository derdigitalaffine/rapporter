from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from .integration_health import sync_with_health
from .models import Family, FamilyEvent, IntegrationSource, Membership

class FakeResponse:
    def __init__(self,*,data=None,text=""):self._data=data;self.text=text
    def json(self):
        if self._data is None:raise ValueError("not json")
        return self._data

class WeatherIntegrationTests(TestCase):
    def setUp(self):
        User=get_user_model();self.user=User.objects.create_user(username="owner-weather",password="test-pass-123");self.family=Family.objects.create(name="Weather Family",slug="weather-family",timezone="Europe/Berlin");Membership.objects.create(family=self.family,user=self.user,role=Membership.Role.OWNER);self.client=APIClient();self.client.force_authenticate(self.user)

    @patch("family.weather_integrations._get")
    def test_dwd_jsonp_feed_is_parsed(self,get_mock):
        get_mock.return_value=FakeResponse(text='warnWetter.loadWarnings({"time":1791560000000,"warnings":{"107312000":[{"state":"Rheinland-Pfalz","type":5,"level":2,"start":1791560000000,"end":1791563600000,"regionName":"Kreisfreie Stadt Kaiserslautern","event":"FROST","headline":"Amtliche WARNUNG vor FROST","description":"Es tritt Frost auf.","instruction":"Frostschutz beachten."}]},"vorabInformation":[],"copyright":"Copyright Deutscher Wetterdienst"});')
        source=IntegrationSource.objects.create(family=self.family,name="DWD Wetterwarnungen",kind=IntegrationSource.Kind.WARNING,config={"adapter":"dwd","region":"Kaiserslautern"});self.assertEqual(sync_with_health(source,force=True),1);warning=FamilyEvent.objects.get(source=source,type="weather.warning");self.assertEqual(warning.payload["provider"],"DWD");self.assertIn("FROST",warning.title)

    @patch("family.weather_integrations._get")
    def test_weather_sync_stores_rich_current_and_exactly_seven_forecast_days(self,get_mock):
        days=[f"2026-10-{day:02d}" for day in range(9,17)]
        get_mock.return_value=FakeResponse(data={"latitude":49.44,"longitude":7.77,"current":{"time":"2026-10-09T19:15","temperature_2m":13.4,"apparent_temperature":12.1,"relative_humidity_2m":74,"weather_code":3,"precipitation":0.0,"wind_speed_10m":8.2},"daily":{"time":days,"weather_code":[3]*8,"temperature_2m_max":[15]*8,"temperature_2m_min":[8]*8,"apparent_temperature_max":[14]*8,"apparent_temperature_min":[7]*8,"precipitation_probability_max":[20]*8,"precipitation_sum":[1.2]*8,"wind_speed_10m_max":[18]*8,"wind_gusts_10m_max":[30]*8,"sunrise":[f"{d}T07:30" for d in days],"sunset":[f"{d}T18:45" for d in days],"uv_index_max":[2.1]*8}})
        source=IntegrationSource.objects.create(family=self.family,name="7-Tage-Wetter",kind=IntegrationSource.Kind.WEATHER,config={"adapter":"weather","latitude":49.44,"longitude":7.77});synced=sync_with_health(source,force=True);self.assertEqual(synced,8);self.assertEqual(FamilyEvent.objects.filter(source=source,type="weather.forecast").count(),7);forecast=FamilyEvent.objects.filter(source=source,type="weather.forecast").first();self.assertEqual(forecast.payload["wind_gust_max"],30);self.assertEqual(forecast.payload["precipitation_sum"],1.2);params=get_mock.call_args.kwargs["params"];self.assertIn("uv_index_max",params["daily"]);self.assertEqual(params["forecast_days"],7)

    def test_weather_api_is_family_scoped_and_calendar_excludes_forecasts(self):
        source=IntegrationSource.objects.create(family=self.family,name="Wetter",kind=IntegrationSource.Kind.WEATHER,config={"latitude":49.44,"longitude":7.77},last_success_at=timezone.now(),last_sync_status="success")
        current=FamilyEvent.objects.create(family=self.family,source=source,external_id="weather:current",type="weather.current",title="12 °C",starts_at=timezone.now()-timedelta(minutes=5),payload={"provider":"Open-Meteo","temperature":12,"weather_code":2})
        for offset in range(7):
            day=(timezone.localdate()+timedelta(days=offset)).isoformat();FamilyEvent.objects.create(family=self.family,source=source,external_id=f"weather:{day}",type="weather.forecast",title=f"Wetter {day}",starts_at=timezone.now()+timedelta(days=offset),payload={"weather_code":2,"temp_min":7,"temp_max":14,"rain_probability":20})
        response=self.client.get(f"/api/weather/?family={self.family.id}");self.assertEqual(response.status_code,200);self.assertEqual(response.data["current"]["temperature"],12);self.assertEqual(len(response.data["days"]),7)
        dashboard=self.client.get(f"/api/dashboard/?family={self.family.id}");self.assertEqual(dashboard.status_code,200);self.assertNotIn(str(current.id),[row["id"] for row in dashboard.data["events"]]);self.assertEqual(dashboard.data["weather"]["current"]["temperature"],12)
        calendar=self.client.get("/api/events/");self.assertEqual(calendar.status_code,200);self.assertFalse(any(row["type"] in {"weather.current","weather.forecast"} for row in calendar.data))
        other=Family.objects.create(name="Other",slug="other-weather");self.assertEqual(self.client.get(f"/api/weather/?family={other.id}").status_code,403)
