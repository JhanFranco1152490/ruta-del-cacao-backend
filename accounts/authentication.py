import jwt
from django.conf import settings
from django.utils import timezone
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed

from .models import RefreshSession, User
from .tokens import decode_token


class CookieJWTAuthentication(BaseAuthentication):
    def authenticate(self, request):
        token = request.COOKIES.get(settings.AUTH_ACCESS_COOKIE)
        if not token:
            return None

        try:
            payload = decode_token(token, "access")
            user = User.objects.get(pk=payload["sub"], is_active=True)
            session = RefreshSession.objects.get(
                pk=payload["sid"],
                user=user,
                revoked_at__isnull=True,
                expires_at__gt=timezone.now(),
            )
        except (jwt.InvalidTokenError, User.DoesNotExist, RefreshSession.DoesNotExist, ValueError):
            raise AuthenticationFailed("La sesión no es válida o ha vencido.") from None

        return user, session

    def authenticate_header(self, request):
        return "Cookie"
