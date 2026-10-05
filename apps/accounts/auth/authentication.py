from django.conf import settings
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.permissions import SAFE_METHODS
from rest_framework_simplejwt.authentication import JWTAuthentication

from apps.common.csrf import enforce_csrf

from ..access import is_effectively_active
from ..acting_producer import resolve_acting_producer


class CookieJWTAuthentication(JWTAuthentication):
    """Lee el token de acceso de la cookie HttpOnly en vez del header Authorization.

    El navegador envía la cookie en cualquier petición al API, incluso desde otro sitio, así
    que toda petición que modifica datos exige además el token CSRF.
    """

    def authenticate(self, request):
        raw_token = request.COOKIES.get(settings.AUTH_ACCESS_COOKIE)
        if not raw_token:
            return None
        validated_token = self.get_validated_token(raw_token)
        user = self.get_user(validated_token)
        if request.method not in SAFE_METHODS:
            enforce_csrf(request)
        user.acting_producer_id = resolve_acting_producer(user, request)
        return user, validated_token

    def get_user(self, validated_token):
        user = super().get_user(validated_token)
        if not is_effectively_active(user):
            # Un token de acceso vigente de una cuenta cuyo productor se desactivó mientras
            # tanto: para quien consume la API significa lo mismo que un token vencido.
            raise AuthenticationFailed()
        return user

    def authenticate_header(self, request):
        # Con un valor aquí DRF responde 401 (y no 403) cuando falta o vence la sesión.
        return 'Cookie realm="api"'
