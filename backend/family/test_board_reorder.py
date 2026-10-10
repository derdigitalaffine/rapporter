from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from .models import BoardPost, Family, Membership


class StableBoardReorderTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user("board-reorder-owner")
        self.guest = User.objects.create_user("board-reorder-guest")
        self.family = Family.objects.create(name="Reorder Family", slug="reorder-family")
        self.other = Family.objects.create(name="Other Reorder Family", slug="other-reorder-family")
        Membership.objects.create(family=self.family, user=self.user, role=Membership.Role.OWNER)
        Membership.objects.create(family=self.family, user=self.guest, role=Membership.Role.GUEST)
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.posts = [
            BoardPost.objects.create(
                family=self.family,
                author=self.user,
                text=f"Pin {index}",
                position=index * 1000,
            )
            for index in range(4)
        ]

    def _positions(self):
        return dict(BoardPost.objects.filter(family=self.family).values_list("id", "position"))

    def _reorder(self, ids):
        return self.client.post(
            "/api/board/reorder/",
            {"family": str(self.family.id), "ids": [str(value) for value in ids]},
            format="json",
        )

    def test_small_move_uses_existing_gap_and_updates_only_moved_pin(self):
        first, second, third, fourth = self.posts
        before = self._positions()

        response = self._reorder([first.id, third.id, second.id, fourth.id])

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(
            response.data["ids"],
            [str(first.id), str(third.id), str(second.id), str(fourth.id)],
        )
        after = self._positions()
        changed = {post_id for post_id, position in after.items() if before[post_id] != position}
        self.assertEqual(changed, {third.id})
        self.assertEqual(after[third.id], 500)
        self.assertEqual(
            list(BoardPost.objects.filter(family=self.family).values_list("id", flat=True)),
            [first.id, third.id, second.id, fourth.id],
        )

    def test_partial_request_moves_named_pin_to_front_without_rewriting_others(self):
        first, second, third, fourth = self.posts
        before = self._positions()

        response = self._reorder([fourth.id])

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(
            response.data["ids"],
            [str(fourth.id), str(first.id), str(second.id), str(third.id)],
        )
        after = self._positions()
        changed = {post_id for post_id, position in after.items() if before[post_id] != position}
        self.assertEqual(changed, {fourth.id})
        self.assertEqual(after[fourth.id], -1000)

    def test_exhausted_integer_gap_falls_back_to_deterministic_rebalance(self):
        first, second, third, fourth = self.posts
        BoardPost.objects.filter(pk=first.id).update(position=0)
        BoardPost.objects.filter(pk=second.id).update(position=1)
        BoardPost.objects.filter(pk=third.id).update(position=2)
        BoardPost.objects.filter(pk=fourth.id).update(position=3)

        response = self._reorder([first.id, third.id, second.id, fourth.id])

        self.assertEqual(response.status_code, 200, response.data)
        rows = list(BoardPost.objects.filter(family=self.family).values_list("id", "position"))
        self.assertEqual(
            rows,
            [(first.id, 0), (third.id, 1000), (second.id, 2000), (fourth.id, 3000)],
        )

    def test_foreign_pin_rejected_atomically_without_position_changes(self):
        foreign = BoardPost.objects.create(
            family=self.other,
            author=self.user,
            text="Foreign pin",
            position=0,
        )
        before = self._positions()

        response = self._reorder([self.posts[1].id, foreign.id])

        self.assertEqual(response.status_code, 400)
        self.assertEqual(self._positions(), before)
        self.assertNotIn("Foreign pin", str(response.data))

    def test_guest_cannot_reorder(self):
        before = self._positions()
        self.client.force_authenticate(self.guest)

        response = self._reorder([self.posts[-1].id])

        self.assertEqual(response.status_code, 403)
        self.assertEqual(self._positions(), before)
