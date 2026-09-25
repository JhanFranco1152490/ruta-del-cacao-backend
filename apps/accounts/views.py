import uuid

from django.conf import settings
from django.middleware.csrf import get_token
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import ensure_csrf_cookie
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.csrf import CsrfProtectedMixin

from .cookies import clear_auth_cookies, set_auth_cookies
from .exceptions import SessionExpired
from .serializers import (
    LoginSerializer,
    PasswordResetConfirmSerializer,
    PasswordResetRequestSerializer,
    SessionSerializer,
)
from .services import (
    confirm_password_reset,
    end_session,
    issue_tokens,
    log_in,
    request_password_reset,
    resolve_login_username,
    rotate_tokens,
)
from .throttles import (
    LoginRateThrottle,
    PasswordResetConfirmThrottle,
    PasswordResetIdentifierThrottle,
    PasswordResetIPThrottle,
)


def request_id_from(request):
    try:
        return uuid.UUID(request.headers.get("X-Request-ID", ""))
    except (TypeError, ValueError):
        return uuid.uuid4()


@method_decorator(ensure_csrf_cookie, name="dispatch")
class CSRFTokenView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        return Response({"csrf_token": get_token(request._request)})


class LoginView(CsrfProtectedMixin, APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [LoginRateThrottle]

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        username = resolve_login_username(
            email=data.get("email"),
            document_type=data.get("document_type"),
            identity_document=data.get("identity_document"),
        )
        user = log_in(
            request,
            username=username,
            password=data["password"],
            request_id=request_id_from(request),
        )
        response = Response(SessionSerializer({"user": user}).data)
        set_auth_cookies(response, *issue_tokens(user))
        return response


class RefreshView(CsrfProtectedMixin, APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        access, refresh = rotate_tokens(request.COOKIES.get(settings.AUTH_REFRESH_COOKIE, ""))
        response = Response(status=status.HTTP_204_NO_CONTENT)
        set_auth_cookies(response, access, refresh)
        return response

    def handle_exception(self, exc):
        response = super().handle_exception(exc)
        if isinstance(exc, SessionExpired):
            clear_auth_cookies(response)
        return response


class LogoutView(CsrfProtectedMixin, APIView):
    # No depende del token de acceso: vence a los 15 minutos y la persona debe poder cerrar
    # la sesión (y revocar la renovación) aunque ya haya vencido.
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        end_session(request.COOKIES.get(settings.AUTH_REFRESH_COOKIE), request_id_from(request))
        response = Response(status=status.HTTP_204_NO_CONTENT)
        clear_auth_cookies(response)
        return response


class CurrentUserView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(SessionSerializer({"user": request.user}).data)


RESET_REQUESTED_DETAIL = (
    "Si el correo está registrado, recibirás instrucciones para restablecer tu contraseña."
)


class PasswordResetRequestView(CsrfProtectedMixin, APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [PasswordResetIPThrottle, PasswordResetIdentifierThrottle]

    def post(self, request):
        serializer = PasswordResetRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        request_password_reset(serializer.validated_data["email"])
        return Response({"detail": RESET_REQUESTED_DETAIL}, status=status.HTTP_202_ACCEPTED)


class PasswordResetConfirmView(CsrfProtectedMixin, APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [PasswordResetConfirmThrottle]

    def post(self, request):
        serializer = PasswordResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        confirm_password_reset(
            data["user"], data["token"], data["new_password"], request_id_from(request)
        )
        return Response(status=status.HTTP_204_NO_CONTENT)
