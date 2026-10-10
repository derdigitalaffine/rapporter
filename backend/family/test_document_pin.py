import uuid

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APIClient

from documents.models import Document, DocumentAccess

from .models import BoardPost, Family, Membership


class DocumentPinAdapterTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.viewer = User.objects.create_user('document-pin-viewer')
        self.document_owner = User.objects.create_user('document-pin-owner')
        self.foreign_owner = User.objects.create_user('document-pin-foreign')
        self.family = Family.objects.create(name='Document Pins', slug='document-pins')
        self.foreign = Family.objects.create(name='Foreign Documents', slug='foreign-documents')
        self.viewer_membership = Membership.objects.create(
            family=self.family,
            user=self.viewer,
            role=Membership.Role.OWNER,
        )
        self.owner_membership = Membership.objects.create(
            family=self.family,
            user=self.document_owner,
            role=Membership.Role.ADULT,
        )
        self.foreign_membership = Membership.objects.create(
            family=self.foreign,
            user=self.foreign_owner,
            role=Membership.Role.OWNER,
        )
        self.client = APIClient()
        self.client.force_authenticate(self.viewer)

    def document(
        self,
        *,
        title,
        family=None,
        owner_membership=None,
        visibility=Document.Visibility.FAMILY,
        archived=False,
        library_visible=True,
        correspondent='',
    ):
        family = family or self.family
        owner_membership = owner_membership or self.owner_membership
        return Document.objects.create(
            family=family,
            owner_membership=owner_membership,
            visibility=visibility,
            title=title,
            correspondent=correspondent,
            canonical_file=f'documents/{title}.pdf',
            mime_type='application/pdf',
            size=1,
            sha256=(title.encode('utf-8').hex() + '0' * 64)[:64],
            archived_at=timezone.now() if archived else None,
            library_visible=library_visible,
        )

    def test_visible_document_pin_has_minimal_preview_and_archived_lifecycle(self):
        document = self.document(title='School contract', correspondent='School Office')

        created = self.client.post(
            '/api/board/',
            {
                'family': str(self.family.id),
                'kind': 'document',
                'target_id': str(document.id),
                'text': '',
            },
            format='json',
        )
        self.assertEqual(created.status_code, 201, created.data)
        self.assertEqual(
            created.data['target'],
            {
                'id': str(document.id),
                'kind': 'document',
                'title': 'School contract',
                'subtitle': 'School Office',
                'lifecycle': 'available',
                'url': f'/api/documents/{document.id}/file/',
            },
        )
        self.assertNotIn('canonical_file', str(created.data['target']))
        self.assertNotIn('sha256', str(created.data['target']))

        document.archived_at = timezone.now()
        document.save(update_fields=['archived_at'])
        row = self.client.get(f'/api/board/?family={self.family.id}').data['results'][0]
        self.assertEqual(row['target']['lifecycle'], 'archived')
        self.assertEqual(row['target']['title'], 'School contract')

        archived = self.document(title='Already archived', archived=True)
        rejected = self.client.post(
            '/api/board/',
            {
                'family': str(self.family.id),
                'kind': 'document',
                'target_id': str(archived.id),
            },
            format='json',
        )
        self.assertEqual(rejected.status_code, 400)
        self.assertFalse(BoardPost.objects.filter(target_id=archived.id).exists())

    def test_inaccessible_and_foreign_documents_are_neutral_on_create(self):
        private = self.document(
            title='Private contract',
            visibility=Document.Visibility.PRIVATE,
        )
        foreign = self.document(
            title='Foreign secret',
            family=self.foreign,
            owner_membership=self.foreign_membership,
        )

        for target_id, secret in (
            (private.id, 'Private contract'),
            (foreign.id, 'Foreign secret'),
        ):
            existing = self.client.post(
                '/api/board/',
                {
                    'family': str(self.family.id),
                    'kind': 'document',
                    'target_id': str(target_id),
                },
                format='json',
            )
            missing = self.client.post(
                '/api/board/',
                {
                    'family': str(self.family.id),
                    'kind': 'document',
                    'target_id': str(uuid.uuid4()),
                },
                format='json',
            )
            self.assertEqual(existing.status_code, 400)
            self.assertEqual(missing.status_code, 400)
            self.assertEqual(existing.data, missing.data)
            self.assertNotIn(secret, str(existing.data))

        self.assertFalse(BoardPost.objects.filter(kind='document').exists())

    def test_domain_managed_document_never_leaks_through_pinboard(self):
        hidden = self.document(
            title='Receipt supporting document',
            correspondent='Secret Merchant',
            library_visible=False,
        )
        post = BoardPost.objects.create(
            family=self.family,
            author=self.viewer,
            kind='document',
            target_id=hidden.id,
        )

        row = self.client.get(f'/api/board/?family={self.family.id}').data['results'][0]
        self.assertEqual(row['id'], str(post.id))
        self.assertEqual(
            row['target'],
            {'id': str(hidden.id), 'kind': 'document', 'available': False},
        )
        self.assertNotIn('Receipt supporting document', str(row))
        self.assertNotIn('Secret Merchant', str(row))

        rejected = self.client.post(
            '/api/board/',
            {
                'family': str(self.family.id),
                'kind': 'document',
                'target_id': str(hidden.id),
            },
            format='json',
        )
        self.assertEqual(rejected.status_code, 400)

    def test_selected_document_is_reauthorized_on_every_read(self):
        selected = self.document(
            title='Selected plan',
            correspondent='Private Advisor',
            visibility=Document.Visibility.SELECTED,
        )
        access = DocumentAccess.objects.create(
            document=selected,
            membership=self.viewer_membership,
            can_view=True,
        )
        created = self.client.post(
            '/api/board/',
            {
                'family': str(self.family.id),
                'kind': 'document',
                'target_id': str(selected.id),
            },
            format='json',
        )
        self.assertEqual(created.status_code, 201, created.data)
        self.assertEqual(created.data['target']['title'], 'Selected plan')

        access.delete()
        row = self.client.get(f'/api/board/?family={self.family.id}').data['results'][0]
        self.assertEqual(
            row['target'],
            {'id': str(selected.id), 'kind': 'document', 'available': False},
        )
        self.assertNotIn('Selected plan', str(row))
        self.assertNotIn('Private Advisor', str(row))

    def test_deleted_document_target_is_neutral(self):
        document = self.document(title='Delete me', correspondent='Hidden correspondent')
        post = BoardPost.objects.create(
            family=self.family,
            author=self.viewer,
            kind='document',
            target_id=document.id,
        )
        target_id = document.id
        document.delete()

        row = self.client.get(f'/api/board/?family={self.family.id}').data['results'][0]
        self.assertEqual(row['id'], str(post.id))
        self.assertEqual(
            row['target'],
            {'id': str(target_id), 'kind': 'document', 'available': False},
        )
        self.assertNotIn('Delete me', str(row))
        self.assertNotIn('Hidden correspondent', str(row))

    def test_document_board_page_batches_acl_resolution(self):
        documents = [
            self.document(title=f'Document {index}')
            for index in range(8)
        ]
        BoardPost.objects.bulk_create(
            [
                BoardPost(
                    family=self.family,
                    author=self.viewer,
                    kind='document',
                    target_id=document.id,
                    position=index,
                )
                for index, document in enumerate(documents)
            ]
        )

        with CaptureQueriesContext(connection) as captured:
            response = self.client.get(f'/api/board/?family={self.family.id}')
        self.assertEqual(response.status_code, 200, response.data)
        document_queries = [
            query['sql']
            for query in captured
            if 'documents_document' in query['sql'].lower()
        ]
        self.assertEqual(len(document_queries), 1, document_queries)
        self.assertEqual(
            {row['target']['title'] for row in response.data['results']},
            {document.title for document in documents},
        )
        self.assertEqual(
            {row['target']['lifecycle'] for row in response.data['results']},
            {'available'},
        )
