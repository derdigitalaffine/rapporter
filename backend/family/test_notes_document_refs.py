from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from documents.models import Document, DocumentAccess

from .models import Family, Membership


class NoteDocumentReferenceTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.alice = User.objects.create_user(username='note-doc-alice')
        self.bob = User.objects.create_user(username='note-doc-bob')
        self.other = User.objects.create_user(username='note-doc-other')
        self.family = Family.objects.create(name='Note docs', slug='note-docs')
        self.other_family = Family.objects.create(name='Other docs', slug='other-note-docs')
        self.alice_membership = Membership.objects.create(
            family=self.family,
            user=self.alice,
            role=Membership.Role.ADULT,
        )
        self.bob_membership = Membership.objects.create(
            family=self.family,
            user=self.bob,
            role=Membership.Role.ADULT,
        )
        self.other_membership = Membership.objects.create(
            family=self.other_family,
            user=self.other,
            role=Membership.Role.ADULT,
        )
        self.client = APIClient()
        self.client.force_authenticate(self.alice)

    def document(self, *, family=None, owner=None, visibility=Document.Visibility.PRIVATE, title='Secure file'):
        family = family or self.family
        owner = owner or self.alice_membership
        return Document.objects.create(
            family=family,
            title=title,
            visibility=visibility,
            owner_membership=owner,
            canonical_file=f'documents/{title}.pdf',
            mime_type='application/pdf',
            size=12,
            sha256=('a' if family == self.family else 'b') * 64,
            page_count=1,
            created_by=owner.user,
        )

    def note_payload(self, document_id):
        return {
            'family': str(self.family.id),
            'title': 'Reference note',
            'body': '',
            'extended_mode': True,
            'blocks': [{'type': 'document', 'document_id': str(document_id)}],
        }

    def test_visible_document_reference_is_stored_as_opaque_id_only(self):
        document = self.document(title='Visible')
        response = self.client.post('/api/notes/', self.note_payload(document.id), format='json')
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data['blocks'], [{'type': 'document', 'document_id': str(document.id)}])
        self.assertNotIn(document.title, str(response.data['blocks']))
        self.assertNotIn('file_url', str(response.data['blocks']))

    def test_new_private_or_cross_family_reference_is_rejected_neutrally(self):
        private_to_bob = self.document(owner=self.bob_membership, title='Bob private')
        foreign = self.document(
            family=self.other_family,
            owner=self.other_membership,
            title='Foreign private',
        )
        for document in (private_to_bob, foreign):
            response = self.client.post('/api/notes/', self.note_payload(document.id), format='json')
            self.assertEqual(response.status_code, 400, response.data)
            self.assertIn('blocks', response.data)

    def test_acl_revocation_hides_document_without_breaking_unrelated_note_edits(self):
        document = self.document(
            owner=self.bob_membership,
            visibility=Document.Visibility.SELECTED,
            title='Temporarily shared',
        )
        access = DocumentAccess.objects.create(
            document=document,
            membership=self.alice_membership,
            can_view=True,
        )
        created = self.client.post('/api/notes/', self.note_payload(document.id), format='json')
        self.assertEqual(created.status_code, 201, created.data)

        access.delete()
        document_list = self.client.get(f'/api/documents/?family={self.family.id}')
        self.assertEqual(document_list.status_code, 200, document_list.data)
        rows = document_list.data.get('results', document_list.data) if isinstance(document_list.data, dict) else document_list.data
        self.assertNotIn(str(document.id), {str(row['id']) for row in rows})

        updated = self.client.patch(
            f"/api/notes/{created.data['id']}/",
            {
                'version': created.data['version'],
                'title': 'Still editable',
                'blocks': created.data['blocks'],
            },
            format='json',
        )
        self.assertEqual(updated.status_code, 200, updated.data)
        self.assertEqual(updated.data['blocks'], created.data['blocks'])
