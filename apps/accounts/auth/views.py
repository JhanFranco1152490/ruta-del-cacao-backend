from django.conf import settings
from django.middleware.csrf import get_token
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import ensure_csrf_cookie
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.csrf import CsrfProtectedMixin
from apps.common.schema import error_responses
from apps.common.serializers import DetailSerializer

from ..exceptions import SessionExpired
from ..requests import request_id_from
from ..throttles import (
    ActivationConfirmThrottle,
    LoginRateThrottle,
    PasswordResetConfirmThrottle,
    PasswordResetIdentifierThrottle,
    PasswordResetIPThrottle,
)
from ..users.activation import confirm_activation
from .cookies import clear_auth_cookies, set_auth_cookies
from .serializers import (
    ActivationConfirmSerializer,
    CsrfTokenSerializer,
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


@method_decorator(ensure_csrf_cookie, name="dispatch")
class CSRFTokenView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    @extend_schema(responses=CsrfTokenSerializer)
    def get(self, request):
        return Response(CsrfTokenSerializer({"csrf_token": get_token(request._request)}).data)


class LoginView(CsrfProtectedMixin, APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [LoginRateThrottle]

    @extend_schema(
        request=LoginSerializer,
        responses={200: SessionSerializer, **error_responses(400, 401, 403, 429)},
    )
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

    @extend_schema(request=None, responses={204: None, **error_responses(401, 403)})
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

    @extend_schema(request=None, responses={204: None, **error_responses(403)})
    def post(self, request):
        end_session(request.COOKIES.get(settings.AUTH_REFRESH_COOKIE), request_id_from(request))
        response = Response(status=status.HTTP_204_NO_CONTENT)
        clear_auth_cookies(response)
        return response


class CurrentUserView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses={200: SessionSerializer, **error_responses(401)})
    def get(self, request):
        return Response(SessionSerializer({"user": request.user}).data)


RESET_REQUESTED_DETAIL = (
    "Si el correo está registrado, recibirás instrucciones para restablecer tu contraseña."
)


class PasswordResetRequestView(CsrfProtectedMixin, APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [PasswordResetIPThrottle, PasswordResetIdentifierThrottle]

    @extend_schema(
        request=PasswordResetRequestSerializer,
        responses={202: DetailSerializer, **error_responses(400, 403, 429)},
    )
    def post(self, request):
        serializer = PasswordResetRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        request_password_reset(serializer.validated_data["email"])
        return Response({"detail": RESET_REQUESTED_DETAIL}, status=status.HTTP_202_ACCEPTED)


class PasswordResetConfirmView(CsrfProtectedMixin, APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [PasswordResetConfirmThrottle]

    @extend_schema(
        request=PasswordResetConfirmSerializer,
        responses={204: None, **error_responses(400, 403, 429)},
    )
    def post(self, request):
        serializer = PasswordResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        confirm_password_reset(
            data["user"], data["token"], data["new_password"], request_id_from(request)
        )
        return Response(status=status.HTTP_204_NO_CONTENT)


class ActivationConfirmView(CsrfProtectedMixin, APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [ActivationConfirmThrottle]

    @extend_schema(
        request=ActivationConfirmSerializer,
        responses={204: None, **error_responses(400, 403, 429)},
    )
    def post(self, request):
        serializer = ActivationConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        confirm_activation(
            data["user"], data["token"], data["new_password"], request_id_from(request)
        )
        return Response(status=status.HTTP_204_NO_CONTENT)
