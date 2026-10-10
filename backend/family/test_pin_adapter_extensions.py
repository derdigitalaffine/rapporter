from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from .models import BoardPost, Family, Membership, Routine, ShoppingList
from .pin_adapters import resolve_pin_targets


class PinAdapterExtensionTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user('pin-extension-user')
        self.family = Family.objects.create(name='Pins', slug='pins')
        self.other = Family.objects.create(name='Other Pins', slug='other-pins')
        Membership.objects.create(family=self.family, user=self.user, role=Membership.Role.ADULT)
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def _pin(self, kind, target_id):
        return self.client.post(
            '/api/board/',
            {
                'family': str(self.family.id),
                'kind': kind,
                'target_id': str(target_id),
                'text': '',
            },
            format='json',
        )

    def test_routine_and_shopping_list_are_pinnable_with_minimal_preview(self):
        routine = Routine.objects.create(family=self.family, name='Abendroutine', active=True)
        shopping_list = ShoppingList.objects.create(
            family=self.family,
            name='Wochenmarkt',
            store='Markthalle',
            archived=False,
        )

        routine_response = self._pin(BoardPost.Kind.ROUTINE, routine.id)
        self.assertEqual(routine_response.status_code, 201, routine_response.data)
        self.assertEqual(routine_response.data['target']['kind'], 'routine')
        self.assertEqual(routine_response.data['target']['title'], 'Abendroutine')
        self.assertEqual(routine_response.data['target']['lifecycle'], 'available')
        self.assertEqual(routine_response.data['target']['url'], f'/?page=tasks&routine={routine.id}')

        list_response = self._pin(BoardPost.Kind.SHOPPING_LIST, shopping_list.id)
        self.assertEqual(list_response.status_code, 201, list_response.data)
        self.assertEqual(list_response.data['target']['kind'], 'shopping_list')
        self.assertEqual(list_response.data['target']['title'], 'Wochenmarkt')
        self.assertEqual(list_response.data['target']['subtitle'], 'Markthalle')
        self.assertEqual(list_response.data['target']['lifecycle'], 'available')
        self.assertEqual(list_response.data['target']['url'], f'/?page=shopping&list={shopping_list.id}')

    def test_archived_targets_remain_resolvable_but_cannot_be_newly_pinned(self):
        routine = Routine.objects.create(family=self.family, name='Archivroutine', active=True)
        shopping_list = ShoppingList.objects.create(family=self.family, name='Archivliste', archived=False)
        routine_pin = self._pin(BoardPost.Kind.ROUTINE, routine.id)
        list_pin = self._pin(BoardPost.Kind.SHOPPING_LIST, shopping_list.id)
        self.assertEqual(routine_pin.status_code, 201)
        self.assertEqual(list_pin.status_code, 201)

        routine.active = False
        routine.save(update_fields=['active'])
        shopping_list.archived = True
        shopping_list.save(update_fields=['archived'])

        rows = self.client.get(f'/api/board/?family={self.family.id}')
        self.assertEqual(rows.status_code, 200)
        targets = {row['kind']: row['target'] for row in rows.data['results']}
        self.assertEqual(targets['routine']['lifecycle'], 'archived')
        self.assertEqual(targets['shopping_list']['lifecycle'], 'archived')

        self.assertEqual(self._pin(BoardPost.Kind.ROUTINE, routine.id).status_code, 400)
        self.assertEqual(self._pin(BoardPost.Kind.SHOPPING_LIST, shopping_list.id).status_code, 400)

    def test_cross_family_targets_are_rejected_without_target_disclosure(self):
        foreign_routine = Routine.objects.create(family=self.other, name='Private foreign routine')
        foreign_list = ShoppingList.objects.create(family=self.other, name='Private foreign list')

        routine_response = self._pin(BoardPost.Kind.ROUTINE, foreign_routine.id)
        list_response = self._pin(BoardPost.Kind.SHOPPING_LIST, foreign_list.id)

        self.assertEqual(routine_response.status_code, 400)
        self.assertEqual(list_response.status_code, 400)
        self.assertNotIn('Private foreign routine', str(routine_response.data))
        self.assertNotIn('Private foreign list', str(list_response.data))
        self.assertFalse(BoardPost.objects.exists())

    def test_deleted_target_becomes_neutral_unavailable(self):
        routine = Routine.objects.create(family=self.family, name='Temporary routine')
        response = self._pin(BoardPost.Kind.ROUTINE, routine.id)
        self.assertEqual(response.status_code, 201)
        pin_id = response.data['id']
        target_id = str(routine.id)

        routine.delete()
        row = self.client.get(f'/api/board/{pin_id}/')
        self.assertEqual(row.status_code, 200)
        self.assertEqual(row.data['target'], {'id': target_id, 'kind': 'routine', 'available': False})
        self.assertNotIn('Temporary routine', str(row.data['target']))

    def test_batch_resolution_uses_one_query_per_adapter_type(self):
        routines = [Routine.objects.create(family=self.family, name=f'Routine {index}') for index in range(3)]
        lists = [ShoppingList.objects.create(family=self.family, name=f'List {index}') for index in range(3)]
        BoardPost.objects.bulk_create(
            [
                *[
                    BoardPost(
                        family=self.family,
                        author=self.user,
                        kind=BoardPost.Kind.ROUTINE,
                        target_id=routine.id,
                    )
                    for routine in routines
                ],
                *[
                    BoardPost(
                        family=self.family,
                        author=self.user,
                        kind=BoardPost.Kind.SHOPPING_LIST,
                        target_id=shopping_list.id,
                    )
                    for shopping_list in lists
                ],
            ]
        )
        posts = list(BoardPost.objects.order_by('id'))

        with self.assertNumQueries(2):
            resolved = resolve_pin_targets(posts, self.user)

        self.assertEqual(len(resolved), 6)
        self.assertTrue(all(target['lifecycle'] == 'available' for target in resolved.values()))
