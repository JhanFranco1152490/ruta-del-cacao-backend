from datetime import timedelta

from django.contrib.auth.models import Group
from django.core.cache import cache
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from apps.accounts.models import User


@override_settings(AUTH_COOKIE_SECURE=False)
class AuthenticationAPITests(APITestCase):
    password = "frase segura de cacao 2026"

    def setUp(self):
        cache.clear()
        self.client = APIClient(enforce_csrf_checks=True)
        self.user = User.objects.create_user(
            email="productor@example.com",
            document_type="CC",
            identity_document="1090123456",
            password=self.password,
            first_name="Persona",
        )
        self.user.groups.add(Group.objects.create(name="producer"))
        self.csrf_token = self._load_csrf_token()

    def _load_csrf_token(self):
        response = self.client.get(reverse("auth-csrf"), secure=True)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        return self.client.cookies["csrftoken"].value

    def _post(self, name, data=None, client=None):
        target_client = client or self.client
        return target_client.post(
            reverse(name),
            data or {},
            format="json",
            secure=True,
            HTTP_ORIGIN="https://testserver",
            HTTP_X_CSRFTOKEN=self.csrf_token,
        )

    def _login(self, identifier=None, password=None, document_type="CC"):
        is_email = identifier is None or "@" in (identifier or "")
        data = {
            "login_method": "email" if is_email else "document",
            "password": password or self.password,
        }
        if is_email:
            data["email"] = identifier or self.user.email
        else:
            data.update({"document_type": document_type, "identity_document": identifier})
        return self._post(
            "auth-login",
            data,
        )

    def test_login_with_identity_document_and_me_endpoint(self):
        response = self._login(identifier=self.user.identity_document)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        me_response = self.client.get(reverse("auth-me"), secure=True)

        self.assertEqual(me_response.status_code, status.HTTP_200_OK)
        self.assertEqual(me_response.data["user"]["email"], self.user.email)

    def test_document_login_normalizes_separators_and_validates_format(self):
        response = self._login(identifier="1090-123.456")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        invalid = self._post(
            "auth-login",
            {
                "login_method": "document",
                "document_type": "CC",
                "identity_document": "10A0123456",
                "password": self.password,
            },
        )
        self.assertEqual(invalid.status_code, status.HTTP_400_BAD_REQUEST)

    def test_nit_login_accepts_normalized_number(self):
        nit_user = User.objects.create_user(
            email="empresa.prueba@example.com",
            document_type="NIT",
            identity_document="900.123.456-7",
            password=self.password,
        )
        response = self._login(identifier="9001234567", document_type="NIT")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(nit_user.identity_document, "9001234567")

    def test_document_numbers_only_allow_digits_and_fifteen_digits(self):
        for document_type in ("CC", "CE", "PPT", "NIT"):
            response = self._post(
                "auth-login",
                {
                    "login_method": "document",
                    "document_type": document_type,
                    "identity_document": "1" * 16,
                    "password": self.password,
                },
            )
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        response = self._post(
            "auth-login",
            {
                "login_method": "document",
                "document_type": "PPT",
                "identity_document": "12345A",
                "password": self.password,
            },
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_invalid_credentials_use_same_message(self):
        wrong_password = self._login(password="contraseña equivocada")
        unknown_user = self._login(identifier="nadie@example.com")

        self.assertEqual(wrong_password.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(unknown_user.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(wrong_password.data, unknown_user.data)

    def test_inactive_account_is_rejected(self):
        self.user.is_active = False
        self.user.save(update_fields=["is_active"])

        response = self._login()

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data["detail"], "La cuenta está inactiva.")

    def test_progressive_lockout_starts_at_three_then_six_minutes(self):
        for _ in range(4):
            self.assertEqual(
                self._login(password="contraseña equivocada").status_code,
                status.HTTP_401_UNAUTHORIZED,
            )
        first_lock = self._login(password="contraseña equivocada")
        self.assertEqual(first_lock.status_code, status.HTTP_403_FORBIDDEN)

        self.user.refresh_from_db()
        self.assertEqual(self.user.lockout_level, 1)
        self.assertGreater(self.user.locked_until, timezone.now() + timedelta(minutes=2))

        self.user.locked_until = timezone.now() - timedelta(seconds=1)
        self.user.save(update_fields=["locked_until"])
        for _ in range(4):
            self._login(password="contraseña equivocada")
        second_lock = self._login(password="contraseña equivocada")

        self.assertEqual(second_lock.status_code, status.HTTP_403_FORBIDDEN)
        self.user.refresh_from_db()
        self.assertEqual(self.user.lockout_level, 2)
        self.assertGreater(self.user.locked_until, timezone.now() + timedelta(minutes=5))

    def test_successful_login_resets_lockout_state(self):
        self.user.failed_login_attempts = 3
        self.user.lockout_level = 2
        self.user.locked_until = timezone.now() - timedelta(seconds=1)
        self.user.save(update_fields=["failed_login_attempts", "lockout_level", "locked_until"])

        response = self._login()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertEqual(self.user.failed_login_attempts, 0)
        self.assertEqual(self.user.lockout_level, 0)
        self.assertIsNone(self.user.locked_until)

    def test_csrf_is_required_for_cookie_creating_requests(self):
        client = APIClient(enforce_csrf_checks=True)

        response = client.post(
            reverse("auth-login"),
            {"login_method": "email", "email": self.user.email, "password": self.password},
            format="json",
            secure=True,
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
