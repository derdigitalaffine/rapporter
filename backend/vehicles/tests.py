import uuid
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient
from entitlements.catalog import COMMERCIAL_CUTOVER_KEY
from entitlements.models import CapabilityDefinition, EntitlementCutover, EntitlementGrant
from family.models import Family, Membership
from .models import Vehicle, Journey


class VehicleApiTests(TestCase):
    def setUp(self):
        user = get_user_model()
        self.alice = user.objects.create_user(username="vehicle-alice")
        self.bob = user.objects.create_user(username="vehicle-bob")
        self.outsider = user.objects.create_user(username="vehicle-other")
        self.child = user.objects.create_user(username="vehicle-child")
        self.family = Family.objects.create(name="Cars", slug="cars")
        self.other = Family.objects.create(name="Other", slug="cars-other")
        for account, family, role in [(self.alice, self.family, "owner"), (self.bob, self.family, "adult"), (self.child, self.family, "child"), (self.outsider, self.other, "owner")]:
            Membership.objects.create(user=account, family=family, role=role)
        CapabilityDefinition.objects.update_or_create(key="vehicles", defaults={"domain": "vehicles", "premium": True})
        self.vehicle = Vehicle.objects.create(family=self.family, name="Family car", odometer=100)
        self.client = APIClient()
        self.client.force_authenticate(self.alice)
        self.base = f"/api/vehicles/{self.vehicle.id}/"

    def start(self, **values):
        payload = {"request_id": str(uuid.uuid4()), "start_odometer": "100.0", **values}
        return self.client.post(self.base + "journeys/", payload, format="json")

    def sample(self, journey, sequence=0, **values):
        return {"sequence": sequence, "timestamp": (journey.started_at+timedelta(seconds=sequence*10+1)).isoformat(), "latitude": 52.5, "longitude": 13.4+sequence*0.0001, "accuracy": 5, **values}

    def test_family_and_adult_permissions_and_no_store(self):
        for account, status in [(self.outsider, 404), (self.child, 403)]:
            self.client.force_authenticate(account)
            for url in [self.base + "fuel/", self.base + "journeys/", f"/api/vehicles/?family={self.family.id}"]:
                response = self.client.get(url)
                self.assertEqual(response.status_code, status)
                self.assertEqual(response["Cache-Control"], "private, no-store")
        self.client.force_authenticate(None)
        self.assertIn(self.client.get(self.base+"fuel/").status_code, [401,403])

    def test_premium_gate_preserves_data(self):
        now = timezone.now()
        EntitlementCutover.objects.create(key=COMMERCIAL_CUTOVER_KEY, cutover_at=now, applied_at=now)
        self.assertEqual(self.client.get(self.base+"fuel/").status_code,403)
        EntitlementGrant.objects.create(family=self.family, origin="promotion", plan_key="premium", reason="test")
        self.assertEqual(self.client.get(self.base+"fuel/").status_code,200)
        self.assertTrue(Vehicle.objects.filter(pk=self.vehicle.pk).exists())

    def test_start_idempotency_exclusivity_and_stop(self):
        token = str(uuid.uuid4())
        first = self.start(request_id=token)
        self.assertEqual(first.status_code,201,first.data)
        self.assertEqual(self.start(request_id=token).data["id"],first.data["id"])
        self.assertEqual(self.start().status_code,409)
        self.client.force_authenticate(self.bob)
        self.assertEqual(self.start().status_code,409)
        self.assertEqual(self.client.get(f'/api/vehicle-journeys/{first.data["id"]}/').status_code,404)
        self.assertEqual(self.client.get(self.base+"journeys/").data,[])
        self.client.force_authenticate(self.alice)
        url=f'/api/vehicle-journeys/{first.data["id"]}/'
        self.assertEqual(self.client.post(url,{"end_odometer":99},format="json").status_code,400)
        stopped=self.client.post(url,{"end_odometer":110},format="json")
        self.assertEqual(stopped.status_code,200)
        self.assertEqual(self.client.post(url,{"end_odometer":120},format="json").data["end_odometer"],"110.0")
        self.vehicle.refresh_from_db()
        self.assertEqual(self.vehicle.odometer,110)
        self.assertEqual(self.client.get(f"/api/vehicles/active/?family={self.family.id}").data,None)

    def test_cross_user_and_cross_family_route_mutation_denied(self):
        trip=self.start().data
        for account in [self.bob,self.outsider,self.child]:
            self.client.force_authenticate(account)
            url=f'/api/vehicle-journeys/{trip["id"]}/'
            for method, endpoint, payload in [("get",url,None),("post",url,{"end_odometer":101}),("post",url+"points/",{"points":[]}),("delete",url,None)]:
                response=getattr(self.client,method)(endpoint,payload,format="json")
                self.assertEqual(response.status_code,404)

    def test_point_batches_retries_conflicts_and_server_distance(self):
        trip=Journey.objects.get(pk=self.start().data["id"])
        url=f"/api/vehicle-journeys/{trip.id}/points/"
        samples=[self.sample(trip,0),self.sample(trip,1)]
        with patch("vehicles.serializers.timezone.now",return_value=trip.started_at+timedelta(seconds=30)):
            self.assertEqual(self.client.post(url,{"points":samples},format="json").status_code,200)
            self.assertEqual(self.client.post(url,{"points":samples},format="json").status_code,200)
            conflict={**samples[0],"longitude":14}
            self.assertEqual(self.client.post(url,{"points":[conflict]},format="json").status_code,409)
        trip.refresh_from_db()
        self.assertEqual(trip.point_count,2)
        self.assertGreater(trip.distance_m,1)
        self.assertLess(trip.distance_m,20)
        self.assertEqual(trip.points.count(),2)
        self.client.post(f"/api/vehicle-journeys/{trip.id}/",{"end_odometer":101},format="json")
        with patch("vehicles.serializers.timezone.now",return_value=trip.started_at+timedelta(seconds=30)):
            self.assertEqual(self.client.post(url,{"points":samples},format="json").status_code,200)
            self.assertEqual(self.client.post(url,{"points":[self.sample(trip,2)]},format="json").status_code,409)

    def test_bad_gps_inputs_are_atomic_and_bounded(self):
        trip=Journey.objects.get(pk=self.start().data["id"])
        url=f"/api/vehicle-journeys/{trip.id}/points/"
        for values in [{"latitude":91},{"longitude":-181},{"accuracy":101},{"sequence":20000},{"sequence":1},{"timestamp":(trip.started_at-timedelta(seconds=1)).isoformat()}]:
            self.assertEqual(self.client.post(url,{"points":[self.sample(trip,**values)]},format="json").status_code,400)
        self.assertEqual(self.client.post(url,{"points":[self.sample(trip)]*101},format="json").status_code,400)
        with patch("vehicles.serializers.timezone.now",return_value=trip.started_at+timedelta(seconds=60)):
            payload=[self.sample(trip),self.sample(trip,1,longitude=20)]
            self.assertEqual(self.client.post(url,{"points":payload},format="json").status_code,400)
        self.assertEqual(trip.points.count(),0)
        self.assertEqual(self.client.post(url, '{"points":[{"latitude":NaN}]}', content_type="application/json").status_code,400)

    def test_fuel_validation_idempotency_and_tenant_binding(self):
        payload={"request_id":str(uuid.uuid4()),"date":timezone.localdate().isoformat(),"odometer":"105","quantity":"40.500","total_cost":"70.00","vehicle":str(uuid.uuid4()),"currency":"EUR"}
        created=self.client.post(self.base+"fuel/",payload,format="json")
        self.assertEqual(created.status_code,201,created.data)
        self.assertEqual(created.data["vehicle"],self.vehicle.pk)
        self.assertEqual(self.client.post(self.base+"fuel/",payload,format="json").data["id"],created.data["id"])
        for field, value in [("quantity",0),("total_cost",-1),("odometer",-1),("currency","!!!")]:
            self.assertEqual(self.client.post(self.base+"fuel/",{**payload,field:value},format="json").status_code,400)
        self.assertEqual(self.vehicle.fuel_entries.count(),1)
        self.vehicle.refresh_from_db()
        self.assertEqual(self.vehicle.odometer,105)

    def test_vehicle_edit_archive_and_vin(self):
        self.assertEqual(self.client.patch(self.base,{"vin":"bad"},format="json").status_code,400)
        self.assertEqual(self.client.patch(self.base,{"name":"Updated","vin":"WVWZZZ1JZXW000001"},format="json").status_code,200)
        self.start()
        self.assertEqual(self.client.patch(self.base,{"archived":True},format="json").status_code,409)

    def test_invalid_family_is_validation_error(self):
        self.assertEqual(self.client.get('/api/vehicles/?family=wrong').status_code,400)
        self.assertEqual(self.client.get('/api/vehicles/').status_code,400)

    def test_database_prevents_concurrent_active_journeys(self):
        self.start()
        with self.assertRaises(IntegrityError),transaction.atomic():
            Journey.objects.create(vehicle=self.vehicle,driver=self.bob,request_id=uuid.uuid4(),started_at=timezone.now(),start_odometer=100)

    def test_completed_journey_cannot_be_hard_deleted(self):
        trip=self.start().data
        url=f'/api/vehicle-journeys/{trip["id"]}/'
        self.assertEqual(self.client.delete(url).status_code,409)
        self.client.post(url,{"end_odometer":100},format="json")
        response=self.client.delete(url)
        self.assertEqual(response.status_code,409)
        self.assertEqual(response.data["code"],"revision_required")
        self.assertEqual(Journey.objects.count(),1)

    def test_osm_map_config_works_without_account_and_is_private(self):
        url=f'/api/vehicles/map-config/?family={self.family.id}'
        response=self.client.get(url)
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.data,{"configured":True,"tile_url":"https://tile.openstreetmap.org/{z}/{x}/{y}.png"})
        self.assertEqual(response["Cache-Control"],"private, no-store")
        for account, status in [(self.outsider,404),(self.child,403)]:
            self.client.force_authenticate(account)
            self.assertEqual(self.client.get(url).status_code,status)
        self.client.force_authenticate(self.alice)
        now=timezone.now()
        EntitlementCutover.objects.create(key=COMMERCIAL_CUTOVER_KEY,cutover_at=now,applied_at=now)
        self.assertEqual(self.client.get(url).status_code,403)

    def test_map_config_rejects_external_hosts_tokens_and_invalid_templates(self):
        url=f'/api/vehicles/map-config/?family={self.family.id}'
        for template in ["https://attacker.example/{z}/{x}/{y}.png","https://tile.openstreetmap.org.attacker.example/{z}/{x}/{y}.png","//attacker.example/{z}/{x}/{y}.png","http://tile.openstreetmap.org/{z}/{x}/{y}.png","https://token@tile.openstreetmap.org/{z}/{x}/{y}.png","https://tile.openstreetmap.org/{z}/{x}/{y}.png?key=secret","https://tile.openstreetmap.org/missing.png"]:
            with self.settings(VEHICLES_OSM_TILE_URL=template):
                self.assertEqual(self.client.get(url).data,{"configured":False})

    @override_settings(VEHICLES_OSM_TILE_URL="/maptiles/{z}/{x}/{y}.png")
    def test_same_origin_osm_service_can_be_configured(self):
        response=self.client.get(f'/api/vehicles/map-config/?family={self.family.id}')
        self.assertEqual(response.data,{"configured":True,"tile_url":"/maptiles/{z}/{x}/{y}.png"})

    def test_legacy_geofabrik_proxy_is_removed(self):
        self.assertEqual(self.client.get(f'/api/vehicles/tiles/0/0/0/?family={self.family.id}').status_code,404)
