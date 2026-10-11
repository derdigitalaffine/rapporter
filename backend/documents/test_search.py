import uuid
from types import SimpleNamespace

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from family.models import Family, Membership

from .models import Document, DocumentAccess, DocumentProcessingRun, DocumentSearchIndex
from .processing import finish_run
from .search import rebuild_document_search_index


class DocumentSearchTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.alice = User.objects.create_user(username="search-alice", password="test-pass-123")
        self.bob = User.objects.create_user(username="search-bob", password="test-pass-123")
        self.cara = User.objects.create_user(username="search-cara", password="test-pass-123")
        self.outsider = User.objects.create_user(username="search-outsider", password="test-pass-123")
        self.family = Family.objects.create(name="Search Family", slug="search-family")
        self.other_family = Family.objects.create(name="Other Search Family", slug="other-search-family")
        self.alice_member = Membership.objects.create(
            family=self.family,
            user=self.alice,
            role=Membership.Role.OWNER,
            display_name="Alice",
        )
        self.bob_member = Membership.objects.create(
            family=self.family,
            user=self.bob,
            role=Membership.Role.ADULT,
            display_name="Bob",
        )
        self.cara_member = Membership.objects.create(
            family=self.family,
            user=self.cara,
            role=Membership.Role.ADULT,
            display_name="Cara",
        )
        self.outsider_member = Membership.objects.create(
            family=self.other_family,
            user=self.outsider,
            role=Membership.Role.OWNER,
            display_name="Outsider",
        )
        self.client = APIClient()

    def auth(self, user):
        self.client.force_authenticate(user)

    def document(self, *, owner=None, family=None, title="Dokument", visibility="family", **kwargs):
        owner = owner or self.alice_member
        family = family or owner.family
        return Document.objects.create(
            family=family,
            kind=kwargs.pop("kind", "generic"),
            title=title,
            document_date=kwargs.pop("document_date", None),
            correspondent=kwargs.pop("correspondent", ""),
            visibility=visibility,
            owner_membership=owner,
            canonical_file=f"documents/{uuid.uuid4()}.pdf",
            mime_type="application/pdf",
            size=100,
            sha256=uuid.uuid4().hex * 2,
            page_count=1,
            pinned=kwargs.pop("pinned", False),
            created_by=owner.user,
            **kwargs,
        )

    def add_processed_text(self, document, text, fields=None):
        run = DocumentProcessingRun.objects.create(
            document=document,
            status=DocumentProcessingRun.Status.READY,
            normalized_text=text,
            processed_at=document.created_at,
        )
        for key, value in fields or []:
            run.extracted_fields.create(key=key, value_json=value, confidence=1)
        rebuild_document_search_index(document.id, processing_run=run)
        return run

    def search(self, user, **params):
        self.auth(user)
        params.setdefault("family", str(self.family.id))
        return self.client.get("/api/documents/search/", params)

    def result_ids(self, response):
        return {row["id"] for row in response.data["results"]}

    def test_search_finds_metadata_ocr_and_allowlisted_reference_fields(self):
        metadata = self.document(
            title="Beitragsbescheid Oktober",
            kind="insurance",
            correspondent="AOK Rheinland-Pfalz",
        )
        rebuild_document_search_index(metadata.id)
        ocr = self.document(title="Neutraler Titel")
        self.add_processed_text(
            ocr,
            "Bitte reichen Sie die Unterlagen mit dem Kennwort Sonnenblume ein.",
            fields=[("reference_number", "AZ4711")],
        )

        for query, expected in [
            ("Beitragsbescheid", metadata),
            ("Rheinland", metadata),
            ("insurance", metadata),
            ("Sonnenblume", ocr),
            ("AZ4711", ocr),
        ]:
            response = self.search(self.alice, q=query)
            self.assertEqual(response.status_code, 200)
            self.assertIn(str(expected.id), self.result_ids(response))

        response = self.search(self.alice, q="Sonnenblume")
        self.assertIn("Sonnenblume", response.data["results"][0]["snippet"])

    def test_acl_is_applied_before_search_and_snippet_generation(self):
        private = self.document(title="Privatakte", visibility=Document.Visibility.PRIVATE)
        self.add_processed_text(private, "Geheimes Suchwort Nebelkrähe")
        selected = self.document(title="Auswahlakte", visibility=Document.Visibility.SELECTED)
        DocumentAccess.objects.create(document=selected, membership=self.bob_member, can_view=True)
        self.add_processed_text(selected, "Geteiltes Suchwort Waldkauz")

        bob_private = self.search(self.bob, q="Nebelkrähe")
        self.assertEqual(bob_private.status_code, 200)
        self.assertEqual(bob_private.data["results"], [])
        self.assertNotIn("Nebelkrähe", str(bob_private.data))

        bob_selected = self.search(self.bob, q="Waldkauz")
        self.assertIn(str(selected.id), self.result_ids(bob_selected))

        cara_selected = self.search(self.cara, q="Waldkauz")
        self.assertEqual(cara_selected.data["results"], [])
        self.assertNotIn(str(selected.id), str(cara_selected.data))

    def test_cross_family_and_foreign_person_filters_fail_closed(self):
        foreign = self.document(
            owner=self.outsider_member,
            family=self.other_family,
            title="Fremde Familienakte",
        )
        rebuild_document_search_index(foreign.id)

        response = self.search(self.alice, family=str(self.other_family.id), q="Familienakte")
        self.assertEqual(response.status_code, 403)
        self.assertNotIn(str(foreign.id), str(response.data))

        response = self.search(self.alice, person=str(self.outsider_member.id))
        self.assertEqual(response.status_code, 404)
        self.assertNotIn(str(self.outsider_member.id), str(response.data))

    def test_filters_run_on_visible_documents_only(self):
        match = self.document(
            title="Versicherung 2026",
            kind="insurance",
            correspondent="AOK",
            visibility=Document.Visibility.SELECTED,
            document_date="2026-10-04",
            pinned=True,
        )
        DocumentAccess.objects.create(document=match, membership=self.bob_member, can_view=True)
        rebuild_document_search_index(match.id)
        other = self.document(
            title="Andere Rechnung",
            kind="invoice",
            correspondent="Stadtwerke",
            document_date="2026-09-01",
        )
        rebuild_document_search_index(other.id)

        response = self.search(
            self.bob,
            kind="insurance",
            visibility="shared",
            person=str(self.bob_member.id),
            correspondent="AOK",
            date_from="2026-10-01",
            date_to="2026-10-31",
            pinned="true",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.result_ids(response), {str(match.id)})
        self.assertNotIn(str(other.id), str(response.data))

    def test_finish_run_reindexes_ocr_text_and_reference_fields(self):
        document = self.document(title="Verarbeitete Akte")
        rebuild_document_search_index(document.id)
        run = DocumentProcessingRun.objects.create(
            document=document,
            status=DocumentProcessingRun.Status.PROCESSING,
            attempts=1,
            claim_token=uuid.uuid4(),
        )
        result = SimpleNamespace(
            fields=[
                {
                    "key": "reference_number",
                    "value_json": "REF-9988",
                    "confidence": 1,
                }
            ],
            extractor="generic",
            language="de",
            text="Neuer OCR Inhalt mit dem Begriff Kieselstein.",
            quality_data={},
        )

        finished = finish_run(run, result, needs_review=False)
        self.assertEqual(finished.status, DocumentProcessingRun.Status.READY)
        index = DocumentSearchIndex.objects.get(document=document)
        self.assertEqual(index.indexed_processing_run_id, run.id)
        self.assertIn(str(document.id), self.result_ids(self.search(self.alice, q="Kieselstein")))
        self.assertIn(str(document.id), self.result_ids(self.search(self.alice, q="REF-9988")))

    def test_metadata_patch_rebuilds_search_index(self):
        document = self.document(title="Alter Titel")
        rebuild_document_search_index(document.id)
        self.auth(self.alice)
        response = self.client.patch(
            f"/api/documents/{document.id}/",
            {"title": "Neuer Suchbegriff"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(str(document.id), self.result_ids(self.search(self.alice, q="Suchbegriff")))
