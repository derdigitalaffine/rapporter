import uuid
from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from family.models import Family, Membership

from .care_service import care_summary, create_handover, handover_payload, record_care_log
from .family_modules import set_module
from .pregnancy_service import create_managed_child

User = get_user_model()

class CareSummaryTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username='care-summary-owner', password='pw')
        self.family = Family.objects.create(name='Care Summary', slug='care-summary', locale='de', timezone='Europe/Berlin')
        Membership.objects.create(family=self.family, user=self.owner, role=Membership.Role.OWNER, display_name='Alex')
        set_module(self.owner, self.family, enabled=True)
        self.baby = create_managed_child(self.owner, self.family, display_name='Mia', birth_date=date.today()-timedelta(days=60), growth_reference_sex='female', client_identity_key=uuid.uuid4())

    def test_active_sleep_is_clipped_to_requested_window(self):
        now = timezone.now()
        started = now - timedelta(hours=26)
        record_care_log(self.owner, self.baby.id, kind='sleep', started_at=started, ended_at=None, client_event_id=uuid.uuid4())
        summary = care_summary(self.owner, self.baby.id, hours=24)
        self.assertEqual(summary['counts']['sleep'], 1)
        self.assertEqual(summary['sleep_minutes'], 1440)
        self.assertEqual(summary['active_sleep_started_at'], started.isoformat())
        handover = create_handover(self.owner, self.baby.id, from_at=now-timedelta(hours=12), to_at=now, note='handover')
        payload = handover_payload(self.owner, handover.id)
        self.assertEqual(payload['counts']['sleep'], 1)
        self.assertEqual(payload['sleep_minutes'], 720)
