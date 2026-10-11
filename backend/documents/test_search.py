from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from family.models import Family, Membership

from .models import Document, DocumentAccess, DocumentProcessingRun, ExtractedField


class DocumentSearchTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.alice = User.objects.create_user(username="search-alice")
        self.bob = User.objects.create_user(username="search-bob")
        self.outsider = User.objects.create_user(username="search-outsider")
        self.family = Family.objects.create(name="Search Family", slug="search-family")
        self.other_family = Family.objects.create(name="Other Search", slug="other-search")
        self.alice_member = Membership.objects.create(
            family=self.family,
            user=self.alice,
            role=Membership.Role.ADULT,
            display_name="Alice",
        )
        self.bob_member = Membership.objects.create(
            family=self.family,
            user=self.bob,
            role=Membership.Role.ADULT,
            display_name="Bob",
        )
        self.outsider_member = Membership.objects.create(
            family=self.other_family,
            user=self.outsider,
            role=Membership.Role.OWNER,
            display_name="Outsider",
        )
        self.client = APIClient()

    def document(
        self,
        *,
        owner=None,
        family=None,
        visibility=Document.Visibility.FAMILY,
        title="Dokument",
        correspondent="",
        kind="generic",
        pinned=False,
        document_date=None,
    ):
        membership = owner or self.alice_member
        target_family = family or membership.family
        return Document.objects.create(
            family=target_family,
            owner_membership=membership,
            visibility=visibility,
            title=title,
            correspondent=correspondent,
            kind=kind,
            pinned=pinned,
            document_date=document_date,
            canonical_file=f"documents/{title}.pdf",
            mime_type="application/pdf",
            size=123,
            sha256=(title.casefold().encode().hex() + "0" * 64)[:64],
            page_count=1,
            processing_status=Document.ProcessingStatus.READY,
            created_by=membership.user,
        )

    def processed(self, document, text, *, reference=None):
        run = DocumentProcessingRun.objects.create(
            document=document,
            status=DocumentProcessingRun.Status.READY,
            normalized_text=text,
            extractor="test",
            processed_at=timezone.now(),
        )
        if reference:
            ExtractedField.objects.create(
                processing_run=run,
                key="reference_number",
                value_json={"value": reference},
                confidence=0.99,
                evidence_text=reference,
            )
        return run

    def search(self, user, **params):
        self.client.force_authenticate(user)
        query = {"family": str(params.pop("family", self.family.id)), **params}
        return self.client.get("/api/documents/search/", query)

    def test_search_indexes_ocr_and_structured_fields_lazily(self):
        document = self.document(
            title="Beitragsbescheid",
            correspondent="AOK",
            kind="letter",
            document_date=date(2026, 10, 4),
        )
        self.processed(document, "Ihre Unterlagen reichen Sie bitte bis Freitag ein.", reference="AZ 4711")

        response = self.search(self.alice, q="Unterlagen")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["id"], str(document.id))
        self.assertIn("Unterlagen", response.data["results"][0]["snippet"])

        reference = self.search(self.alice, q="4711")
        self.assertEqual(reference.data["count"], 1)
        self.assertEqual(reference.data["results"][0]["id"], str(document.id))

    def test_private_ocr_text_never_leaks_to_other_member(self):
        secret = self.document(
            owner=self.bob_member,
            visibility=Document.Visibility.PRIVATE,
            title="Privat",
        )
        self.processed(secret, "einzigartiges-supergeheimnis-778899")
        visible = self.document(title="Öffentlich")
        self.processed(visible, "harmloser Familieninhalt")

        response = self.search(self.alice, q="supergeheimnis")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["results"], [])
        self.assertNotIn(str(secret.id), str(response.data))

        owner_response = self.search(self.bob, q="supergeheimnis")
        self.assertEqual(owner_response.data["count"], 1)
        self.assertEqual(owner_response.data["results"][0]["id"], str(secret.id))

    def test_selected_document_requires_explicit_access(self):
        selected = self.document(
            owner=self.bob_member,
            visibility=Document.Visibility.SELECTED,
            title="Freigegebener Elternbrief",
        )
        self.processed(selected, "Klassenfahrt Zustimmung")

        hidden = self.search(self.alice, q="Klassenfahrt")
        self.assertEqual(hidden.data["results"], [])

        DocumentAccess.objects.create(document=selected, membership=self.alice_member, can_view=True)
        visible = self.search(self.alice, q="Klassenfahrt")
        self.assertEqual(visible.data["count"], 1)
        self.assertEqual(visible.data["results"][0]["id"], str(selected.id))

    def test_cross_family_search_fails_closed(self):
        other = self.document(
            owner=self.outsider_member,
            family=self.other_family,
            title="Andere Familie",
        )
        self.processed(other, "fremder Familieninhalt")

        response = self.search(self.alice, family=self.other_family.id, q="Familieninhalt")
        self.assertEqual(response.status_code, 404)

    def test_filters_apply_after_authorization(self):
        target = self.document(
            title="Versicherung",
            correspondent="AOK Nord",
            kind="insurance",
            pinned=True,
            document_date=date(2026, 10, 4),
        )
        self.processed(target, "Versicherungsbescheid")
        other = self.document(
            owner=self.bob_member,
            title="Rechnung",
            correspondent="Werkstatt",
            kind="invoice",
            pinned=False,
            document_date=date(2025, 1, 3),
        )
        self.processed(other, "Rechnung Reifen")

        response = self.search(
            self.alice,
            kind="insurance",
            visibility="family",
            pinned="true",
            person=str(self.alice_member.id),
            correspondent="AOK",
            date_from="2026-01-01",
            date_to="2026-12-31",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual([row["id"] for row in response.data["results"]], [str(target.id)])

    def test_search_material_refreshes_after_new_processing_run(self):
        document = self.document(title="Dynamisch")
        self.processed(document, "alter Inhalt")
        first = self.search(self.alice, q="alter")
        self.assertEqual(first.data["count"], 1)

        run = self.processed(document, "brandneuer Suchbegriff")
        DocumentProcessingRun.objects.filter(pk=run.pk).update(updated_at=timezone.now())
        second = self.search(self.alice, q="brandneuer")
        self.assertEqual(second.data["count"], 1)
        self.assertEqual(second.data["results"][0]["id"], str(document.id))
