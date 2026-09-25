import re
from datetime import timedelta

from django.contrib.auth.models import Group
from django.core import mail
from django.core.cache import cache
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from apps.accounts.models import AuthenticationEvent, PasswordResetToken, RefreshSession, User


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

    def test_login_with_email_sets_secure_session_and_returns_identity(self):
        response = self._login()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["user"]["roles"], ["producer"])
        self.assertIn("cacao_access", response.cookies)
        self.assertIn("cacao_refresh", response.cookies)
        self.assertTrue(response.cookies["cacao_access"]["httponly"])
        self.assertEqual(
            AuthenticationEvent.objects.filter(
                event_type=AuthenticationEvent.EventType.LOGIN_SUCCEEDED
            ).count(),
            1,
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

    def test_refresh_rotates_token_and_rejects_replay(self):
        self._login()
        original_refresh = self.client.cookies["cacao_refresh"].value

        response = self._post("auth-refresh")

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertNotEqual(self.client.cookies["cacao_refresh"].value, original_refresh)

        replay_client = APIClient(enforce_csrf_checks=True)
        replay_client.cookies["csrftoken"] = self.csrf_token
        replay_client.cookies["cacao_refresh"] = original_refresh
        replay = self._post("auth-refresh", client=replay_client)

        self.assertEqual(replay.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_logout_revokes_session_and_clears_cookies(self):
        self._login()

        response = self._post("auth-logout")

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(response.cookies["cacao_access"].value, "")
        self.assertFalse(RefreshSession.objects.filter(revoked_at__isnull=True).exists())
        self.assertEqual(
            self.client.get(reverse("auth-me"), secure=True).status_code,
            status.HTTP_401_UNAUTHORIZED,
        )

    def test_password_reset_response_does_not_reveal_account(self):
        existing = self._post("password-reset", {"email": self.user.email})
        unknown = self._post("password-reset", {"email": "nadie@example.com"})

        self.assertEqual(existing.status_code, status.HTTP_202_ACCEPTED)
        self.assertEqual(unknown.status_code, status.HTTP_202_ACCEPTED)
        self.assertEqual(existing.data, unknown.data)
        self.assertEqual(len(mail.outbox), 1)

    def test_password_reset_changes_password_and_revokes_sessions(self):
        self._login()
        request_response = self._post("password-reset", {"email": self.user.email})
        self.assertEqual(request_response.status_code, status.HTTP_202_ACCEPTED)
        raw_token = re.search(r"token=([^\s]+)", mail.outbox[0].body).group(1)
        new_password = "una nueva frase segura 2026"

        confirm_response = self._post(
            "password-reset-confirm",
            {
                "token": raw_token,
                "new_password": new_password,
                "new_password_confirmation": new_password,
            },
        )

        self.assertEqual(confirm_response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(RefreshSession.objects.filter(revoked_at__isnull=True).exists())
        self.assertEqual(
            self._login(password=self.password).status_code, status.HTTP_401_UNAUTHORIZED
        )
        self.assertEqual(self._login(password=new_password).status_code, status.HTTP_200_OK)

    def test_password_reset_token_is_single_use(self):
        self._post("password-reset", {"email": self.user.email})
        raw_token = re.search(r"token=([^\s]+)", mail.outbox[0].body).group(1)
        payload = {
            "token": raw_token,
            "new_password": "una nueva frase segura 2026",
            "new_password_confirmation": "una nueva frase segura 2026",
        }

        first = self._post("password-reset-confirm", payload)
        second = self._post("password-reset-confirm", payload)

        self.assertEqual(first.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(second.status_code, status.HTTP_400_BAD_REQUEST)

    def test_expired_password_reset_token_is_rejected(self):
        self._post("password-reset", {"email": self.user.email})
        raw_token = re.search(r"token=([^\s]+)", mail.outbox[0].body).group(1)
        PasswordResetToken.objects.update(expires_at=timezone.now() - timedelta(seconds=1))

        response = self._post(
            "password-reset-confirm",
            {
                "token": raw_token,
                "new_password": "una nueva frase segura 2026",
                "new_password_confirmation": "una nueva frase segura 2026",
            },
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_short_password_is_rejected(self):
        self._post("password-reset", {"email": self.user.email})
        raw_token = re.search(r"token=([^\s]+)", mail.outbox[0].body).group(1)

        response = self._post(
            "password-reset-confirm",
            {
                "token": raw_token,
                "new_password": "corta",
                "new_password_confirmation": "corta",
            },
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("new_password", response.data)

    def test_csrf_is_required_for_cookie_creating_requests(self):
        client = APIClient(enforce_csrf_checks=True)

        response = client.post(
            reverse("auth-login"),
            {"login_method": "email", "email": self.user.email, "password": self.password},
            format="json",
            secure=True,
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_browser_csrf_token_and_cors_allow_frontend_login(self):
        with override_settings(
            CORS_ALLOWED_ORIGINS=["http://localhost:3000"],
            CSRF_TRUSTED_ORIGINS=["http://localhost:3000"],
        ):
            client = APIClient(enforce_csrf_checks=True)
            csrf = client.get(reverse("auth-csrf"), HTTP_ORIGIN="http://localhost:3000")
            self.assertEqual(csrf["Access-Control-Allow-Origin"], "http://localhost:3000")
            self.assertEqual(csrf["Access-Control-Allow-Credentials"], "true")
            response = client.post(
                reverse("auth-login"),
                {"login_method": "email", "email": self.user.email, "password": self.password},
                format="json",
                HTTP_ORIGIN="http://localhost:3000",
                HTTP_X_CSRFTOKEN=csrf.data["csrf_token"],
            )
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertEqual(client.get(reverse("auth-me")).status_code, status.HTTP_200_OK)

    def test_password_reset_accepts_eight_and_fifty_characters(self):
        for password in ["C@cao!7x", "C@cao!7x" + "z" * 42]:
            with self.subTest(length=len(password)):
                self._post("password-reset", {"email": self.user.email})
                token = re.search(r"token=([^\s]+)", mail.outbox[-1].body).group(1)
                response = self._post(
                    "password-reset-confirm",
                    {
                        "token": token,
                        "new_password": password,
                        "new_password_confirmation": password,
                    },
                )
                self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
                self.assertEqual(self._login(password=password).status_code, status.HTTP_200_OK)

    def test_password_reset_rejects_more_than_fifty_characters(self):
        response = self._post(
            "password-reset-confirm",
            {
                "token": "test-token",
                "new_password": "C@cao!7x" + "z" * 43,
                "new_password_confirmation": "C@cao!7x" + "z" * 43,
            },
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("new_password", response.data)
