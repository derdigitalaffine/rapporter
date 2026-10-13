import io
import tempfile
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.storage import FileSystemStorage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.utils import timezone
from pypdf import PdfWriter
from rest_framework.test import APIClient

from entitlements.catalog import COMMERCIAL_CUTOVER_KEY
from entitlements.models import EntitlementCutover, EntitlementGrant
from .models import Expense, ExpenseLedger, get_default_expense_ledger


class FinanceContractTests(TestCase):
    def setUp(self):
        from family.models import Family, Membership
        self.user = get_user_model().objects.create_user(username="finance", password="test-pass-123")
        self.family = Family.objects.create(name="Finance", slug="finance")
        self.member = Membership.objects.create(user=self.user, family=self.family, role="owner")
        self.other = Family.objects.create(name="Other", slug="finance-other")
        self.ledger = get_default_expense_ledger(self.family)
        self.expense = Expense.objects.create(family=self.family, ledger=self.ledger, paid_by=self.member, total_amount="10.00", category="Food")
        self.client = APIClient(); self.client.force_authenticate(self.user)
        now = timezone.now()
        EntitlementCutover.objects.create(key=COMMERCIAL_CUTOVER_KEY, cutover_at=now, applied_at=now)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        storage = patch("documents.storage.default_storage", FileSystemStorage(location=self.temp.name))
        storage.start(); self.addCleanup(storage.stop)

    def grant(self):
        return EntitlementGrant.objects.create(family=self.family, origin="admin_grant", plan_key="premium")

    def test_light_denied_at_read_write_and_receipt_boundaries(self):
        for path in [f"/api/expenses/?family={self.family.id}", f"/api/expense-ledgers/?family={self.family.id}", f"/api/expense-budgets/?family={self.family.id}", f"/api/expenses/balance/?family={self.family.id}", f"/api/expenses/settlement-plan/?family={self.family.id}", f"/api/expenses/settlements/?family={self.family.id}", f"/api/expense-ledgers/{self.ledger.id}/budget-summary/", f"/api/expenses/{self.expense.id}/receipt-file/", f"/api/expenses/{self.expense.id}/budget-allocations/"]:
            self.assertEqual(self.client.get(path).status_code, 403, path)
        self.assertEqual(self.client.post('/api/expenses/', {'family':str(self.family.id),'total_amount':'2.00'},format='json').status_code,403)
        self.assertEqual(self.client.get('/api/expenses/').data['results'], [])
        self.assertEqual(self.client.patch(f'/api/expenses/{self.expense.id}/', {'title':'blocked'},format='json').status_code,404)
        self.expense.refresh_from_db(); self.assertEqual(self.expense.total_amount,10)

    def test_premium_multiple_accounts_category_and_revocation(self):
        grant = self.grant()
        account = self.client.post('/api/expense-ledgers/', {'family':str(self.family.id),'name':'Savings','base_currency':'EUR'},format='json')
        self.assertEqual(account.status_code,201,account.data)
        created = self.client.post('/api/expenses/', {'family':str(self.family.id),'ledger':account.data['id'],'total_amount':'20.00','funding_source':'shared','category':'Home'},format='json')
        self.assertEqual(created.status_code,201,created.data)
        self.assertEqual(str(created.data['ledger']),str(account.data['id'])); self.assertEqual(created.data['category'],'Home')
        rows = self.client.get(f"/api/expenses/?family={self.family.id}&ledger={account.data['id']}").data['results']
        self.assertEqual([row['id'] for row in rows],[created.data['id']])
        grant.active=False; grant.save()
        self.assertEqual(self.client.get(f'/api/expenses/?family={self.family.id}').status_code,403)
        self.assertEqual(Expense.objects.filter(family=self.family).count(),2)

    def test_pdf_receipt_content_detection_account_and_private_url(self):
        self.grant()
        ledger = ExpenseLedger.objects.create(family=self.family,name='Card')
        writer=PdfWriter(); writer.add_blank_page(width=100,height=100)
        raw=io.BytesIO(); writer.write(raw)
        response=self.client.post('/api/expenses/receipt/', {'family':str(self.family.id),'ledger':str(ledger.id),'receipt':SimpleUploadedFile('receipt.jpg',raw.getvalue(),content_type='image/jpeg')},format='multipart')
        self.assertEqual(response.status_code,202,response.data)
        self.assertEqual(response.data['receipt_mime'],'application/pdf')
        self.assertEqual(str(response.data['ledger']),str(ledger.id))
        url=f"/api/expenses/{response.data['id']}/receipt-file/"
        file=self.client.get(url)
        self.assertEqual(file['Content-Type'],'application/pdf')
        self.assertEqual(b''.join(file.streaming_content),raw.getvalue())
        self.assertEqual(file['Cache-Control'],'private, no-store')
        fake=self.client.post('/api/expenses/receipt/', {'family':str(self.family.id),'receipt':SimpleUploadedFile('fake.pdf',b'%PDF-fake',content_type='application/pdf')},format='multipart')
        self.assertEqual(fake.status_code,400)
        self.assertEqual(self.client.post('/api/expenses/receipt/', {'family':str(self.family.id),'ledger':str(get_default_expense_ledger(self.other).id),'receipt':SimpleUploadedFile('x.pdf',raw.getvalue())},format='multipart').status_code,400)

    def test_cross_family_ids_are_rejected_even_when_premium(self):
        self.grant()
        other_ledger=get_default_expense_ledger(self.other)
        self.assertEqual(self.client.get(f'/api/expense-ledgers/{other_ledger.id}/').status_code,404)
        self.assertEqual(self.client.post('/api/expenses/', {'family':str(self.family.id),'ledger':str(other_ledger.id),'total_amount':'2.00','funding_source':'shared'},format='json').status_code,400)
