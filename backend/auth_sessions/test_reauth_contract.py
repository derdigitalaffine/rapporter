from django.test import SimpleTestCase
from rest_framework.views import exception_handler

from .service import FreshAuthenticationRequired


class FreshAuthenticationContractTests(SimpleTestCase):
    def test_reauth_required_exposes_machine_readable_code(self):
        response = exception_handler(FreshAuthenticationRequired(), {})

        self.assertIsNotNone(response)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.data["code"], "reauth_required")
        self.assertEqual(response.data["detail"], "Bitte bestätige deine Identität erneut.")
