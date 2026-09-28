from django.conf import settings
from rest_framework_simplejwt.settings import api_settings

ACCESS_COOKIE_PATH = "/api/"
# El refresh solo viaja a los endpoints de sesión, no en cada petición al API.
REFRESH_COOKIE_PATH = "/api/auth/"


def set_auth_cookies(response, access: str, refresh: str) -> None:
    options = {
        "secure": settings.AUTH_COOKIE_SECURE,
        "httponly": True,
        "samesite": settings.AUTH_COOKIE_SAMESITE,
    }
    response.set_cookie(
        settings.AUTH_ACCESS_COOKIE,
        access,
        max_age=int(api_settings.ACCESS_TOKEN_LIFETIME.total_seconds()),
        path=ACCESS_COOKIE_PATH,
        **options,
    )
    response.set_cookie(
        settings.AUTH_REFRESH_COOKIE,
        refresh,
        max_age=int(api_settings.REFRESH_TOKEN_LIFETIME.total_seconds()),
        path=REFRESH_COOKIE_PATH,
        **options,
    )


def clear_auth_cookies(response) -> None:
    # Borrar exige el mismo path con el que se creó la cookie.
    samesite = settings.AUTH_COOKIE_SAMESITE
    response.delete_cookie(settings.AUTH_ACCESS_COOKIE, path=ACCESS_COOKIE_PATH, samesite=samesite)
    response.delete_cookie(
        settings.AUTH_REFRESH_COOKIE, path=REFRESH_COOKIE_PATH, samesite=samesite
    )
