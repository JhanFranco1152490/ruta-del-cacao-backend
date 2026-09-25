import uuid

import jwt
from django.conf import settings
from django.db import transaction
from django.middleware.csrf import CsrfViewMiddleware, get_token
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import ensure_csrf_cookie
from rest_framework import status
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import AuthenticationEvent, RefreshSession
from .serializers import (
    LoginSerializer,
    PasswordResetConfirmSerializer,
    PasswordResetRequestSerializer,
)
from .services import (
    AccountLockedError,
    InactiveAccountError,
    InvalidCredentialsError,
    authenticate_user,
    confirm_password_reset,
    cookie_options,
    record_authentication_event,
    request_password_reset,
    serialize_user,
)
from .throttles import LoginRateThrottle, PasswordResetIdentifierThrottle, PasswordResetIPThrottle
from .tokens import decode_token, fingerprint, issue_token_pair


def request_id_from(request):
    try:
        return uuid.UUID(request.headers.get("X-Request-ID", ""))
    except (TypeError, ValueError):
        return uuid.uuid4()


def enforce_csrf(request):
    check = CsrfViewMiddleware(lambda _: None)
    failure = check.process_view(request._request, None, (), {})
    if failure:
        raise PermissionDenied("La validación CSRF falló.")


def set_auth_cookies(response, access_token, refresh_token):
    options = cookie_options()
    response.set_cookie(
        settings.AUTH_ACCESS_COOKIE,
        access_token,
        max_age=int(settings.AUTH_ACCESS_TOKEN_LIFETIME.total_seconds()),
        path="/api/",
        **options,
    )
    response.set_cookie(
        settings.AUTH_REFRESH_COOKIE,
        refresh_token,
        max_age=int(settings.AUTH_REFRESH_TOKEN_LIFETIME.total_seconds()),
        path="/api/auth/",
        **options,
    )


def clear_auth_cookies(response):
    response.delete_cookie(
        settings.AUTH_ACCESS_COOKIE,
        path="/api/",
        samesite=settings.AUTH_COOKIE_SAMESITE,
    )
    response.delete_cookie(
        settings.AUTH_REFRESH_COOKIE,
        path="/api/auth/",
        samesite=settings.AUTH_COOKIE_SAMESITE,
    )


@method_decorator(ensure_csrf_cookie, name="dispatch")
class CSRFTokenView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        return Response({"csrf_token": get_token(request._request)})


class LoginView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [LoginRateThrottle]

    def post(self, request):
        enforce_csrf(request)
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        request_id = request_id_from(request)

        try:
            user = authenticate_user(
                login_method=serializer.validated_data["login_method"],
                password=serializer.validated_data["password"],
                request_id=request_id,
                email=serializer.validated_data.get("email"),
                document_type=serializer.validated_data.get("document_type"),
                identity_document=serializer.validated_data.get("identity_document"),
            )
        except InvalidCredentialsError:
            return Response(
                {"detail": "Usuario o contraseña incorrectos."},
                status=status.HTTP_401_UNAUTHORIZED,
            )
        except InactiveAccountError:
            return Response(
                {"detail": "La cuenta está inactiva."},
                status=status.HTTP_403_FORBIDDEN,
            )
        except AccountLockedError as error:
            return Response(
                {
                    "detail": "La cuenta está bloqueada temporalmente.",
                    "retry_after": error.retry_after,
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        access_token, refresh_token, _ = issue_token_pair(user)
        response = Response({"user": serialize_user(user)})
        set_auth_cookies(response, access_token, refresh_token)
        return response


class RefreshView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    @transaction.atomic
    def post(self, request):
        enforce_csrf(request)
        token = request.COOKIES.get(settings.AUTH_REFRESH_COOKIE)
        if not token:
            return Response(status=status.HTTP_401_UNAUTHORIZED)

        try:
            payload = decode_token(token, "refresh")
            session = RefreshSession.objects.select_for_update().get(
                pk=payload["sid"],
                token_fingerprint=fingerprint(payload["jti"]),
                revoked_at__isnull=True,
                expires_at__gt=timezone.now(),
                user__is_active=True,
            )
        except (jwt.InvalidTokenError, RefreshSession.DoesNotExist, ValueError):
            response = Response(status=status.HTTP_401_UNAUTHORIZED)
            clear_auth_cookies(response)
            return response

        session.revoked_at = timezone.now()
        session.save(update_fields=["revoked_at"])
        access_token, refresh_token, _ = issue_token_pair(session.user)
        response = Response(status=status.HTTP_204_NO_CONTENT)
        set_auth_cookies(response, access_token, refresh_token)
        return response


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        enforce_csrf(request)
        session = request.auth
        if session.revoked_at is None:
            session.revoked_at = timezone.now()
            session.save(update_fields=["revoked_at"])
            record_authentication_event(
                AuthenticationEvent.EventType.SESSION_REVOKED,
                AuthenticationEvent.Outcome.SUCCESS,
                request_id_from(request),
                request.user,
            )
        response = Response(status=status.HTTP_204_NO_CONTENT)
        clear_auth_cookies(response)
        return response


class CurrentUserView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response({"user": serialize_user(request.user)})


RESET_REQUESTED_DETAIL = (
    "Si el correo está registrado, recibirás instrucciones para restablecer tu contraseña."
)


class PasswordResetRequestView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [PasswordResetIPThrottle, PasswordResetIdentifierThrottle]

    def post(self, request):
        serializer = PasswordResetRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        request_password_reset(serializer.validated_data["email"])
        return Response({"detail": RESET_REQUESTED_DETAIL}, status=status.HTTP_202_ACCEPTED)


class PasswordResetConfirmView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [PasswordResetIPThrottle]

    def post(self, request):
        enforce_csrf(request)
        serializer = PasswordResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        confirm_password_reset(
            serializer.validated_data["user"],
            serializer.validated_data["new_password"],
            request_id_from(request),
        )
        return Response(status=status.HTTP_204_NO_CONTENT)
