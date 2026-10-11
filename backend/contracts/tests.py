from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from documents.models import Document, DocumentLink, DocumentProcessingRun, ExtractedField
from family.models import Family, FamilyEvent, Membership, Task

from .models import ContractReminder


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
            "cancellation_period": "30 Tage",
            "visibility": "private",
        }
        payload.update(overrides)
        response = self.client.post("/api/contracts/", payload, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        return response.data

    def _document(self, *, family=None, membership=None, owner=None, sha="a"):
        family = family or self.family
        membership = membership or self.owner_membership
        owner = owner or self.owner
        return Document.objects.create(
            family=family,
            kind="contract",
            title="Contract PDF",
            visibility=Document.Visibility.PRIVATE if family == self.family else Document.Visibility.FAMILY,
            owner_membership=membership,
            canonical_file=f"documents/{sha}.pdf",
            mime_type="application/pdf",
            size=12,
            sha256=sha * 64,
            page_count=1,
            created_by=owner,
        )

    def test_manual_private_contract_is_complete_and_isolated(self):
        created = self.create_contract()
        self.assertEqual(created["documents"], [])
        self.assertEqual(created["cancellation_period"], "30 Tage")
        self.assertEqual(created["derived_dates"][-1]["key"], "cancellation_deadline")
        self.assertEqual(created["derived_dates"][-1]["date"], "2026-12-02")

        other_client = APIClient()
        other_client.force_authenticate(self.other)
        listing = other_client.get(f"/api/contracts/?family={self.family.id}")
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(listing.data, [])
        self.assertEqual(other_client.get(f"/api/contracts/{created['id']}/").status_code, 404)

    def test_calendar_month_cancellation_period_is_not_approximated_as_days(self):
        created = self.create_contract(end_date="2027-03-31", cancellation_period="1 Monat")
        deadline = next(item for item in created["derived_dates"] if item["key"] == "cancellation_deadline")
        self.assertEqual(deadline["date"], "2027-02-28")
        self.assertEqual(deadline["source_type"], "derived")

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
        self.assertIn(response.status_code, {403, 404})
        self.assertEqual(outsider.get(f"/api/contracts/{created['id']}/").status_code, 404)

    def test_document_link_requires_same_family_and_visibility(self):
        created = self.create_contract()
        document = self._document()
        response = self.client.post(f"/api/contracts/{created['id']}/documents/", {"document": str(document.id)}, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["documents"][0]["id"], str(document.id))
        self.assertTrue(DocumentLink.objects.filter(document=document, domain_type=DocumentLink.DomainType.CONTRACT, object_id=created["id"]).exists())

        foreign = self._document(family=self.other_family, membership=self.outsider_membership, owner=self.outsider, sha="b")
        self.assertEqual(self.client.post(f"/api/contracts/{created['id']}/documents/", {"document": str(foreign.id)}, format="json").status_code, 404)
        self.assertEqual(self.client.delete(f"/api/contracts/{created['id']}/documents/{document.id}/").status_code, 204)

    def test_prefill_maps_document_core_contract_keys_and_preserves_provenance(self):
        document = self._document(sha="c")
        run = DocumentProcessingRun.objects.create(
            document=document,
            status=DocumentProcessingRun.Status.REVIEW,
            extractor="pypdf",
            normalized_text="Kundennummer: C-7788\nMindestlaufzeit: 24 Monate\nKündigungsfrist: 3 Monate\nBetrag: 49,99 EUR monatlich",
        )
        ExtractedField.objects.create(
            processing_run=run,
            key="contract.number",
            value_json={"value": "V-12345"},
            confidence="0.9600",
            page=1,
            evidence_text="Vertragsnummer: V-12345",
            source_type=ExtractedField.SourceType.EXPLICIT,
        )
        ExtractedField.objects.create(
            processing_run=run,
            key="contract.start_date",
            value_json={"value": "01.02.2026"},
            confidence="0.9500",
            page=1,
            evidence_text="Vertragsbeginn: 01.02.2026",
            source_type=ExtractedField.SourceType.EXPLICIT,
        )
        ExtractedField.objects.create(
            processing_run=run,
            key="text.page",
            value_json={"text": run.normalized_text, "source": "embedded"},
            confidence="1.0000",
            page=1,
            evidence_text=run.normalized_text,
            source_type=ExtractedField.SourceType.EXPLICIT,
        )
        response = self.client.get(f"/api/contracts/prefill/?family={self.family.id}&document={document.id}")
        self.assertEqual(response.status_code, 200, response.data)
        suggestions = {item["field"]: item for item in response.data["suggestions"]}
        self.assertEqual(suggestions["contract_number"]["value"], "V-12345")
        self.assertEqual(suggestions["contract_number"]["page"], 1)
        self.assertEqual(suggestions["contract_number"]["source_type"], "explicit")
        self.assertEqual(suggestions["start_date"]["value"], "2026-02-01")
        self.assertEqual(suggestions["customer_number"]["value"], "C-7788")
        self.assertEqual(suggestions["minimum_term_months"]["value"], 24)
        self.assertEqual(suggestions["minimum_term_months"]["source_type"], "derived")
        self.assertEqual(suggestions["cancellation_period"]["value"], "3 Monate")
        self.assertEqual(suggestions["amount"]["value"], "49.99")
        self.assertEqual(suggestions["billing_interval"]["value"], "monthly")

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
        created = self.create_contract(end_date=None, start_date="2026-01-31", minimum_term_months=1, cancellation_period="1 Woche")
        term_end = next(item for item in created["derived_dates"] if item["key"] == "minimum_term_end")
        deadline = next(item for item in created["derived_dates"] if item["key"] == "cancellation_deadline")
        self.assertEqual(term_end["date"], "2026-02-28")
        self.assertEqual(term_end["source_type"], "derived")
        self.assertEqual(deadline["date"], "2026-02-21")
