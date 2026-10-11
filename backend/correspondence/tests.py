from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from documents.models import Document, DocumentLink, DocumentProcessingRun, ExtractedField
from expenses.models import Expense
from family.context_models import ContextLink
from family.models import Family, Membership, ShoppingItem, ShoppingList, Task


class CorrespondenceApiTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user(username="letter-owner", password="pw")
        self.other = User.objects.create_user(username="letter-other", password="pw")
        self.outsider = User.objects.create_user(username="letter-outsider", password="pw")
        self.family = Family.objects.create(name="Alpha letters", slug="alpha-letters")
        self.foreign = Family.objects.create(name="Beta letters", slug="beta-letters")
        self.owner_membership = Membership.objects.create(family=self.family, user=self.owner, role=Membership.Role.OWNER)
        Membership.objects.create(family=self.family, user=self.other, role=Membership.Role.ADULT)
        self.foreign_membership = Membership.objects.create(family=self.foreign, user=self.outsider, role=Membership.Role.OWNER)
        self.client = APIClient(); self.client.force_authenticate(self.owner)

    def document(self, visibility=Document.Visibility.PRIVATE, sha="d"):
        document = Document.objects.create(family=self.family, kind="correspondence", title="Bescheid.pdf", visibility=visibility, owner_membership=self.owner_membership, canonical_file=f"documents/{sha}.pdf", mime_type="application/pdf", size=100, sha256=sha*64, page_count=1, created_by=self.owner, processing_status=Document.ProcessingStatus.REVIEW)
        run = DocumentProcessingRun.objects.create(document=document, status=DocumentProcessingRun.Status.REVIEW, extractor="pypdf", normalized_text="Absender: Stadtverwaltung\nEmpfänger: Erika Beispiel\nDatum: 10.10.2026\nBetreff: Gebührenbescheid\nAktenzeichen: AZ-42/7\nBetrag: 49,90 EUR\nIBAN: DE89 3704 0044 0532 0130 00\nBitte überweisen Sie den Betrag bis spätestens 31.10.2026.\nKontakt: amt@example.de")
        ExtractedField.objects.create(processing_run=run, key="text.page", value_json={"text":run.normalized_text,"source":"embedded"}, confidence="1.0000", page=1, evidence_text=run.normalized_text)
        return document

    def test_review_is_deterministic_and_deadline_has_evidence(self):
        document = self.document()
        response = self.client.get(f"/api/correspondence/{document.id}/review/")
        self.assertEqual(response.status_code, 200, response.data)
        suggestions = {row["field"]: row for row in response.data["suggestions"]}
        self.assertEqual(suggestions["sender"]["value"], "Stadtverwaltung")
        self.assertEqual(suggestions["deadline"]["value"], "2026-10-31")
        self.assertIn("31.10.2026", suggestions["deadline"]["evidence_text"])
        self.assertEqual(suggestions["action_text"]["source_type"], "suggestion")
        self.assertTrue(suggestions["action_text"]["uncertain"])
        self.assertIn("Genannte Frist", response.data["summary"])

    def test_manual_correction_persists_and_summary_prefers_confirmed_values(self):
        document = self.document(sha="e")
        response = self.client.patch(f"/api/correspondence/{document.id}/review/", {"data":{"sender":"Korrigierte Behörde","deadline":"2026-11-02","action_text":"Unterlagen senden"},"reviewed":True}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["review"]["data"]["sender"], "Korrigierte Behörde")
        self.assertIn("2026-11-02", response.data["summary"])
        self.assertIn("Bestätigte Handlung", response.data["summary"])

    def test_private_document_blocks_family_wide_projection(self):
        document = self.document(sha="f")
        self.client.patch(f"/api/correspondence/{document.id}/review/", {"data":{"subject":"Gebühren","amount":"49.90","deadline":"2026-10-31"}}, format="json")
        for action in ("task","event","expense"):
            response = self.client.post(f"/api/correspondence/{document.id}/actions/", {"action":action,"confirmed":True}, format="json")
            self.assertEqual(response.status_code, 409, response.data)
        self.assertEqual(Task.objects.count(),0); self.assertEqual(Expense.objects.count(),0)

    def test_actions_require_confirmation_and_keep_document_backlinks(self):
        document = self.document(Document.Visibility.FAMILY, sha="g")
        self.client.patch(f"/api/correspondence/{document.id}/review/", {"data":{"subject":"Gebühren","amount":"49.90","deadline":"2026-10-31","action_text":"Gebühr erledigen"}}, format="json")
        path=f"/api/correspondence/{document.id}/actions/"
        self.assertEqual(self.client.post(path,{"action":"task"},format="json").status_code,400)
        task=self.client.post(path,{"action":"task","confirmed":True},format="json"); self.assertEqual(task.status_code,201,task.data)
        self.assertTrue(DocumentLink.objects.filter(document=document,domain_type=DocumentLink.DomainType.TASK,object_id=task.data["id"]).exists())
        expense=self.client.post(path,{"action":"expense","confirmed":True},format="json"); self.assertEqual(expense.status_code,201,expense.data)
        created_expense=Expense.objects.get(id=expense.data["id"]); self.assertEqual(created_expense.receipt_document_id,document.id)

    def test_shopping_uses_context_link_and_same_family_list(self):
        document=self.document(Document.Visibility.FAMILY,sha="h")
        shopping=ShoppingList.objects.create(family=self.family,name="Besorgungen")
        response=self.client.post(f"/api/correspondence/{document.id}/actions/",{"action":"shopping","confirmed":True,"shopping_list":str(shopping.id),"title":"Unterlagen besorgen"},format="json")
        self.assertEqual(response.status_code,201,response.data)
        item=ShoppingItem.objects.get(id=response.data["id"]); self.assertEqual(item.shopping_list,shopping)
        self.assertTrue(ContextLink.objects.filter(family=self.family,source_type="document",source_id=document.id,context_type="shopping_item",context_id=item.id,relation_key="correspondence.action").exists())

    def test_foreign_member_cannot_read_or_mutate_review(self):
        document=self.document(sha="i")
        outsider=APIClient(); outsider.force_authenticate(self.outsider)
        self.assertEqual(outsider.get(f"/api/correspondence/{document.id}/review/").status_code,404)
        self.assertEqual(outsider.patch(f"/api/correspondence/{document.id}/review/",{"data":{"sender":"leak"}},format="json").status_code,404)
