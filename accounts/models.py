import uuid

from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.models.functions import Lower

from .managers import UserManager


class User(AbstractUser):
    class DocumentType(models.TextChoices):
        CC = "CC", "Cédula de ciudadanía"
        CE = "CE", "Cédula de extranjería"
        PPT = "PPT", "Permiso por Protección Temporal"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    username = None
    email = models.EmailField(unique=True)
    document_type = models.CharField(max_length=3, choices=DocumentType.choices)
    identity_document = models.CharField(max_length=50)
    failed_login_attempts = models.PositiveSmallIntegerField(default=0)
    lockout_level = models.PositiveSmallIntegerField(default=0)
    locked_until = models.DateTimeField(null=True, blank=True)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["document_type", "identity_document"]

    class Meta:
        constraints = [
            models.UniqueConstraint(Lower("email"), name="accounts_user_email_ci_unique"),
            models.UniqueConstraint(
                fields=["document_type", "identity_document"],
                name="accounts_user_document_type_number_unique",
            ),
        ]

    def clean(self):
        super().clean()
        self.email = self.__class__.objects.normalize_email(self.email).lower()

    def __str__(self):
        return self.email


class RefreshSession(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="refresh_sessions")
    token_fingerprint = models.CharField(max_length=64, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [models.Index(fields=["user", "revoked_at"])]


class PasswordResetToken(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="password_reset_tokens")
    token_digest = models.CharField(max_length=64, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)


class AuthenticationEvent(models.Model):
    class EventType(models.TextChoices):
        LOGIN_SUCCEEDED = "login_succeeded", "Inicio de sesión exitoso"
        LOGIN_FAILED = "login_failed", "Inicio de sesión fallido"
        ACCOUNT_LOCKED = "account_locked", "Cuenta bloqueada"
        PASSWORD_RESET = "password_reset", "Contraseña restablecida"
        SESSION_REVOKED = "session_revoked", "Sesión revocada"

    class Outcome(models.TextChoices):
        SUCCESS = "success", "Exitoso"
        FAILURE = "failure", "Fallido"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event_type = models.CharField(max_length=32, choices=EventType.choices)
    outcome = models.CharField(max_length=16, choices=Outcome.choices)
    user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="authentication_events",
    )
    request_id = models.UUIDField(default=uuid.uuid4, editable=False)
    occurred_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-occurred_at"]
