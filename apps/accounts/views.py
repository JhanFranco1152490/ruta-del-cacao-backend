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
    AccountLockedError,
    InactiveAccountError,
    InvalidCredentialsError,
    authenticate_user,
    confirm_password_reset,
    end_session,
    issue_tokens,
    request_password_reset,
    rotate_tokens,
)
from .throttles import LoginRateThrottle, PasswordResetIdentifierThrottle, PasswordResetIPThrottle


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

    # Transitorio: el manejo de errores con Response directas se reemplaza en la Tarea 7.
    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            user = authenticate_user(
                login_method=serializer.validated_data["login_method"],
                password=serializer.validated_data["password"],
                request_id=request_id_from(request),
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
                {"detail": "La cuenta está inactiva."}, status=status.HTTP_403_FORBIDDEN
            )
        except AccountLockedError as error:
            return Response(
                {
                    "detail": "La cuenta está bloqueada temporalmente.",
                    "retry_after": error.retry_after,
                },
                status=status.HTTP_403_FORBIDDEN,
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
    throttle_classes = [PasswordResetIPThrottle]

    def post(self, request):
        serializer = PasswordResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        confirm_password_reset(
            serializer.validated_data["user"],
            serializer.validated_data["new_password"],
            request_id_from(request),
        )
        return Response(status=status.HTTP_204_NO_CONTENT)
