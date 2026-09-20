import hashlib
import secrets
import uuid
from datetime import datetime
from datetime import timezone as datetime_timezone

import jwt
from django.conf import settings
from django.utils import timezone

from .models import RefreshSession


def fingerprint(value):
    return hashlib.sha256(value.encode()).hexdigest()


def _base_payload(user, token_type, expires_at, **claims):
    now = datetime.now(tz=datetime_timezone.utc)
    return {
        "aud": settings.AUTH_JWT_AUDIENCE,
        "exp": expires_at,
        "iat": now,
        "iss": settings.AUTH_JWT_ISSUER,
        "jti": str(uuid.uuid4()),
        "sub": str(user.pk),
        "type": token_type,
        **claims,
    }


def _encode(payload):
    return jwt.encode(payload, settings.AUTH_JWT_SIGNING_KEY, algorithm="HS256")


def decode_token(token, expected_type):
    payload = jwt.decode(
        token,
        settings.AUTH_JWT_SIGNING_KEY,
        algorithms=["HS256"],
        audience=settings.AUTH_JWT_AUDIENCE,
        issuer=settings.AUTH_JWT_ISSUER,
        options={"require": ["aud", "exp", "iat", "iss", "jti", "sub", "type"]},
    )
    if payload["type"] != expected_type:
        raise jwt.InvalidTokenError("Tipo de token inválido.")
    return payload


def issue_token_pair(user):
    refresh_expires_at = timezone.now() + settings.AUTH_REFRESH_TOKEN_LIFETIME
    refresh_payload = _base_payload(user, "refresh", refresh_expires_at)
    session = RefreshSession.objects.create(
        user=user,
        token_fingerprint=fingerprint(refresh_payload["jti"]),
        expires_at=refresh_expires_at,
    )
    refresh_payload["sid"] = str(session.pk)

    access_expires_at = timezone.now() + settings.AUTH_ACCESS_TOKEN_LIFETIME
    access_payload = _base_payload(user, "access", access_expires_at, sid=str(session.pk))
    return _encode(access_payload), _encode(refresh_payload), session


def generate_password_reset_token():
    return secrets.token_urlsafe(32)
