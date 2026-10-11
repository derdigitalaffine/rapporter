from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from .models import Family


class SuperadminFamilyPaginationTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.admin = User.objects.create_superuser(username="family-pagination-admin", password="pw")
        self.client = APIClient()
        self.client.force_authenticate(self.admin)
        self.alpha = Family.objects.create(name="Alpha Family", slug="alpha-family", status=Family.Status.ACTIVE)
        self.beta = Family.objects.create(name="Beta Family", slug="beta-family", status=Family.Status.ACTIVE)
        self.delta = Family.objects.create(name="Delta Family", slug="delta-family", status=Family.Status.SUSPENDED)
        self.gamma = Family.objects.create(name="Gamma Family", slug="gamma-family", status=Family.Status.ACTIVE)

    def test_legacy_family_list_without_pagination_params_keeps_array_contract(self):
        response = self.client.get("/api/superadmin/families/")

        self.assertEqual(response.status_code, 200, response.data)
        self.assertIsInstance(response.data, list)
        self.assertEqual([row["name"] for row in response.data], [
            "Alpha Family",
            "Beta Family",
            "Delta Family",
            "Gamma Family",
        ])

    def test_paginated_contract_filters_and_sorts_before_count_and_slice(self):
        response = self.client.get(
            "/api/superadmin/families/?status=active&sort=-name&limit=2&offset=1"
        )

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["count"], 3)
        self.assertEqual(response.data["limit"], 2)
        self.assertEqual(response.data["offset"], 1)
        self.assertEqual(response.data["sort"], "-name")
        self.assertEqual(response.data["status"], Family.Status.ACTIVE)
        self.assertEqual(
            [row["name"] for row in response.data["results"]],
            ["Beta Family", "Alpha Family"],
        )

    def test_offset_alone_uses_default_page_size_and_search_applies_before_count(self):
        response = self.client.get("/api/superadmin/families/?q=Family&offset=2")

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["count"], 4)
        self.assertEqual(response.data["limit"], 100)
        self.assertEqual(response.data["offset"], 2)
        self.assertEqual(
            [row["name"] for row in response.data["results"]],
            ["Delta Family", "Gamma Family"],
        )

    def test_invalid_pagination_values_fail_closed(self):
        cases = (
            ("limit=nope", "integer"),
            ("limit=0", "page size"),
            ("limit=201", "page size"),
            ("offset=-1", "non-negative"),
        )
        for query, expected in cases:
            with self.subTest(query=query):
                response = self.client.get(f"/api/superadmin/families/?{query}")
                self.assertEqual(response.status_code, 400, response.data)
                self.assertIn(expected, response.data["detail"].lower())
