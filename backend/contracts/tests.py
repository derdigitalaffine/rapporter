from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from documents.models import Document, DocumentLink, DocumentProcessingRun, ExtractedField
from family.models import Family, FamilyEvent, Membership, Task

from .models import Contract, ContractReminder


class ContractApiTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user(username="owner", password="pw")
        self.other = User.objects.create_user(username="other", password="pw")
        self.outsider = User.objects.create_user(username="outsider", password="pw")
        self.family = Family.objects.create(name="Alpha", slug="alpha")
        self.other_family = Family.objects.create(name="Beta", slug="beta")
        self.owner_membership = Membership.objects.create(family=self.family, user=self.owner, role=Membership.Role.OWNER)
        self.other_membership = Membership.objects.create(family=self.family, user=self.other, role=Membership.Role.ADULT)
        self.outsider_membership = Membership.objects.create(family=self.other_family, user=self.outsider, role=Membership.Role.OWNER)
        self.client = APIClient()
        self.client.force_authenticate(self.owner)

    def create_contract(self, **overrides):
        payload = {
            "family": str(self.family.id),
            "title": "Internet",
            "provider": "Example Net",
            "start_date": "2026-01-01",
            "end_date": "2027-01-01",
            "cancellation_period_days": 30,
            "visibility": "private",
        }
        payload.update(overrides)
        response = self.client.post("/api/contracts/", payload, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        return response.data

    def test_manual_private_contract_is_complete_and_isolated(self):
        created = self.create_contract()
        self.assertEqual(created["documents"], [])
        self.assertEqual(created["derived_dates"][-1]["key"], "cancellation_deadline")
        self.assertEqual(created["derived_dates"][-1]["date"], "2026-12-02")

        other_client = APIClient()
        other_client.force_authenticate(self.other)
        listing = other_client.get(f"/api/contracts/?family={self.family.id}")
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(listing.data, [])
        self.assertEqual(other_client.get(f"/api/contracts/{created['id']}/").status_code, 404)

    def test_family_contract_is_visible_but_not_mutable_by_default(self):
        created = self.create_contract(visibility="family")
        other_client = APIClient()
        other_client.force_authenticate(self.other)
        listing = other_client.get(f"/api/contracts/?family={self.family.id}")
        self.assertEqual([row["id"] for row in listing.data], [created["id"]])
        update = other_client.patch(f"/api/contracts/{created['id']}/", {"title": "Changed"}, format="json")
        self.assertEqual(update.status_code, 404)

    def test_cross_family_create_and_read_fail_closed(self):
        created = self.create_contract()
        outsider = APIClient()
        outsider.force_authenticate(self.outsider)
        response = outsider.post("/api/contracts/", {"family": str(self.family.id), "title": "Leak"}, format="json")
        self.assertEqual(response.status_code, 403)
        self.assertEqual(outsider.get(f"/api/contracts/{created['id']}/").status_code, 404)

    def test_document_link_requires_same_family_and_visibility(self):
        created = self.create_contract()
        document = Document.objects.create(
            family=self.family,
            kind="contract",
            title="Contract PDF",
            visibility=Document.Visibility.PRIVATE,
            owner_membership=self.owner_membership,
            canonical_file="documents/a.pdf",
            mime_type="application/pdf",
            size=12,
            sha256="a" * 64,
            page_count=1,
            created_by=self.owner,
        )
        response = self.client.post(f"/api/contracts/{created['id']}/documents/", {"document": str(document.id)}, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["documents"][0]["id"], str(document.id))
        self.assertTrue(DocumentLink.objects.filter(document=document, domain_type=DocumentLink.DomainType.CONTRACT, object_id=created["id"]).exists())

        foreign = Document.objects.create(
            family=self.other_family,
            kind="contract",
            title="Foreign",
            visibility=Document.Visibility.FAMILY,
            owner_membership=self.outsider_membership,
            canonical_file="documents/b.pdf",
            mime_type="application/pdf",
            size=12,
            sha256="b" * 64,
            page_count=1,
            created_by=self.outsider,
        )
        self.assertEqual(self.client.post(f"/api/contracts/{created['id']}/documents/", {"document": str(foreign.id)}, format="json").status_code, 404)
        self.assertEqual(self.client.delete(f"/api/contracts/{created['id']}/documents/{document.id}/").status_code, 204)

    def test_prefill_preserves_confidence_evidence_and_source_type(self):
        document = Document.objects.create(
            family=self.family,
            kind="contract",
            title="Contract PDF",
            visibility=Document.Visibility.PRIVATE,
            owner_membership=self.owner_membership,
            canonical_file="documents/c.pdf",
            mime_type="application/pdf",
            size=12,
            sha256="c" * 64,
            page_count=1,
            created_by=self.owner,
        )
        run = DocumentProcessingRun.objects.create(document=document, status=DocumentProcessingRun.Status.REVIEW, extractor="contract")
        ExtractedField.objects.create(
            processing_run=run,
            key="cancellation_period_days",
            value_json=90,
            confidence="0.9200",
            page=2,
            evidence_text="Kündigungsfrist drei Monate",
            source_type=ExtractedField.SourceType.EXPLICIT,
        )
        ExtractedField.objects.create(
            processing_run=run,
            key="end_date",
            value_json="2027-09-30",
            confidence="0.6100",
            page=2,
            evidence_text="berechnet",
            source_type=ExtractedField.SourceType.DERIVED,
        )
        response = self.client.get(f"/api/contracts/prefill/?family={self.family.id}&document={document.id}")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["suggestions"][0]["page"], 2)
        self.assertEqual(response.data["suggestions"][0]["source_type"], "explicit")
        self.assertEqual(response.data["suggestions"][1]["source_type"], "derived")

    def test_follow_ups_need_confirmation_and_private_data_does_not_leak(self):
        private = self.create_contract()
        path = f"/api/contracts/{private['id']}/actions/"
        self.assertEqual(self.client.post(path, {"action": "reminder"}, format="json").status_code, 400)
        reminder = self.client.post(path, {"action": "reminder", "confirmed": True}, format="json")
        self.assertEqual(reminder.status_code, 201, reminder.data)
        self.assertEqual(ContractReminder.objects.count(), 1)
        blocked = self.client.post(path, {"action": "task", "confirmed": True}, format="json")
        self.assertEqual(blocked.status_code, 409)
        self.assertEqual(Task.objects.count(), 0)

        family_contract = self.create_contract(title="Family Internet", visibility="family")
        family_path = f"/api/contracts/{family_contract['id']}/actions/"
        task = self.client.post(family_path, {"action": "task", "confirmed": True}, format="json")
        event = self.client.post(family_path, {"action": "event", "confirmed": True}, format="json")
        self.assertEqual(task.status_code, 201, task.data)
        self.assertEqual(event.status_code, 201, event.data)
        self.assertEqual(Task.objects.filter(family=self.family).count(), 1)
        self.assertEqual(FamilyEvent.objects.filter(family=self.family, type="contract").count(), 1)

    def test_minimum_term_end_is_marked_derived(self):
        created = self.create_contract(end_date=None, start_date="2026-01-31", minimum_term_months=1, cancellation_period_days=7)
        term_end = next(item for item in created["derived_dates"] if item["key"] == "minimum_term_end")
        self.assertEqual(term_end["date"], "2026-02-28")
        self.assertEqual(term_end["source_type"], "derived")
