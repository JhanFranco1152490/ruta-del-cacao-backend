from dataclasses import dataclass
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from .models import AuthenticationEvent, User

LOCKOUT_MINUTES = (3, 6, 12, 24, 48, 60)
DUMMY_PASSWORD_HASH = make_password("timing-only-password-value")


class InvalidCredentialsError(Exception):
    pass


class InactiveAccountError(Exception):
    pass


@dataclass
class AccountLockedError(Exception):
    retry_after: int


def record_authentication_event(event_type, outcome, request_id, user=None):
    AuthenticationEvent.objects.create(
        event_type=event_type,
        outcome=outcome,
        request_id=request_id,
        user=user,
    )


def authenticate_user(identifier, password, request_id):
    normalized_identifier = identifier.strip()
    query = Q(email__iexact=normalized_identifier) | Q(identity_document=normalized_identifier)
    error = None

    with transaction.atomic():
        user = User.objects.select_for_update().filter(query).first()

        if user is None:
            check_password(password, DUMMY_PASSWORD_HASH)
            record_authentication_event(
                AuthenticationEvent.EventType.LOGIN_FAILED,
                AuthenticationEvent.Outcome.FAILURE,
                request_id,
            )
            error = InvalidCredentialsError()
        else:
            now = timezone.now()
            if user.locked_until and user.locked_until > now:
                retry_after = max(1, int((user.locked_until - now).total_seconds()))
                error = AccountLockedError(retry_after)
            elif not user.is_active:
                record_authentication_event(
                    AuthenticationEvent.EventType.LOGIN_FAILED,
                    AuthenticationEvent.Outcome.FAILURE,
                    request_id,
                    user,
                )
                error = InactiveAccountError()
            elif not user.check_password(password):
                error = _register_failed_attempt(user, request_id, now)
            else:
                _register_successful_login(user, request_id, now)
                return user

    raise error


def _register_failed_attempt(user, request_id, now):
    user.failed_login_attempts += 1
    if user.failed_login_attempts >= 5:
        user.failed_login_attempts = 0
        user.lockout_level = min(user.lockout_level + 1, len(LOCKOUT_MINUTES))
        user.locked_until = now + timedelta(minutes=LOCKOUT_MINUTES[user.lockout_level - 1])
        user.save(update_fields=["failed_login_attempts", "lockout_level", "locked_until"])
        record_authentication_event(
            AuthenticationEvent.EventType.ACCOUNT_LOCKED,
            AuthenticationEvent.Outcome.FAILURE,
            request_id,
            user,
        )
        return AccountLockedError(LOCKOUT_MINUTES[user.lockout_level - 1] * 60)

    user.save(update_fields=["failed_login_attempts"])
    record_authentication_event(
        AuthenticationEvent.EventType.LOGIN_FAILED,
        AuthenticationEvent.Outcome.FAILURE,
        request_id,
        user,
    )
    return InvalidCredentialsError()


def _register_successful_login(user, request_id, now):
    user.failed_login_attempts = 0
    user.lockout_level = 0
    user.locked_until = None
    user.last_login = now
    user.save(
        update_fields=[
            "failed_login_attempts",
            "lockout_level",
            "locked_until",
            "last_login",
        ]
    )
    record_authentication_event(
        AuthenticationEvent.EventType.LOGIN_SUCCEEDED,
        AuthenticationEvent.Outcome.SUCCESS,
        request_id,
        user,
    )


def serialize_user(user):
    roles = list(user.groups.order_by("name").values_list("name", flat=True))
    permissions = sorted(user.get_all_permissions())
    return {
        "id": str(user.pk),
        "email": user.email,
        "roles": roles,
        "permissions": permissions,
    }


def cookie_options():
    return {
        "secure": settings.AUTH_COOKIE_SECURE,
        "httponly": True,
        "samesite": settings.AUTH_COOKIE_SAMESITE,
    }
