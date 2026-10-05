import uuid

from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F, Q
from django.db.models.functions import Lower

from apps.common.choices import DocumentType
from apps.common.validators import (
    strip_document_separators,
    validate_document_digits,
    validate_phone,
)

from .managers import UserManager

EMAIL_UNIQUE_CONSTRAINT = "accounts_user_email_ci_unique"
DOCUMENT_UNIQUE_CONSTRAINT = "accounts_user_document_type_number_unique"


class User(AbstractUser):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    username = None
    email = models.EmailField(unique=True)
    document_type = models.CharField(max_length=3, choices=DocumentType.choices)
    identity_document = models.CharField(max_length=15)
    phone = models.CharField(max_length=25, null=True, blank=True, validators=[validate_phone])
    # Nula en el Administrador; obligatoria en las demás cuentas (HU-03 lo aplica en el
    # servicio, porque la regla depende del rol y los roles son muchos a muchos).
    producer = models.ForeignKey(
        "producers.Producer",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="accounts",
    )
    # Productor bajo el que opera un superusuario en esta petición. No es un campo: lo fija la
    # autenticación de cada petición y nunca se guarda.
    acting_producer_id = None

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["document_type", "identity_document"]

    class Meta:
        constraints = [
            models.UniqueConstraint(Lower("email"), name=EMAIL_UNIQUE_CONSTRAINT),
            models.UniqueConstraint(
                fields=["document_type", "identity_document"],
                name=DOCUMENT_UNIQUE_CONSTRAINT,
            ),
        ]
        permissions = [
            ("users_view", "Puede consultar cuentas"),
            ("users_create", "Puede crear cuentas"),
            ("users_update", "Puede actualizar cuentas"),
            ("users_change_status", "Puede activar o desactivar cuentas"),
            ("users_delete", "Puede eliminar cuentas creadas por error"),
        ]
        ordering = ["last_name", "first_name", "id"]

    @property
    def effective_producer_id(self):
        """El productor bajo el que se actúa: el elegido por un superusuario, o el propio."""
        if self.is_superuser and self.acting_producer_id is not None:
            return self.acting_producer_id
        return self.producer_id

    def clean(self):
        super().clean()
        self.email = self.__class__.objects.normalize_email(self.email).lower()
        self.identity_document = strip_document_separators(self.identity_document)
        # Se valida aquí y no como validador del campo: los validadores de campo corren antes
        # de clean(), y así rechazarían "900.123.456-7" sin dejar que se normalice.
        try:
            validate_document_digits(self.identity_document)
        except ValidationError as error:
            raise ValidationError({"identity_document": error.messages}) from error

    def __str__(self):
        return self.email


class Role(models.Model):
    """Un rol es un grupo de Django con dueño: quién lo creó y si puede tocarse.

    La autorización (`has_perm`, `ActionPermission`) sigue leyendo los permisos del grupo; esta
    tabla solo agrega de quién es el rol y si es de los que nadie edita ni borra.
    """

    class Kind(models.TextChoices):
        FIXED = "fixed", "Fijo"
        PREDEFINED = "predefined", "Predefinido"
        CUSTOM = "custom", "Propio"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    group = models.OneToOneField("auth.Group", on_delete=models.PROTECT, related_name="role")
    # Nulo en los propios: no tienen un identificador estable entre productores.
    code = models.CharField(max_length=32, unique=True, null=True, blank=True)
    kind = models.CharField(max_length=10, choices=Kind.choices)
    producer = models.ForeignKey(
        "producers.Producer",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="roles",
    )
    name = models.CharField(max_length=100)
    description = models.CharField(max_length=255, blank=True, default="")

    class Meta:
        constraints = [
            models.UniqueConstraint(
                Lower("name"),
                condition=Q(producer__isnull=True),
                name="accounts_role_system_name_ci_unique",
            ),
            models.UniqueConstraint(
                Lower("name"),
                F("producer"),
                condition=Q(producer__isnull=False),
                name="accounts_role_producer_name_ci_unique",
            ),
            models.CheckConstraint(
                condition=(
                    Q(kind="custom", producer__isnull=False)
                    | (~Q(kind="custom") & Q(producer__isnull=True))
                ),
                name="accounts_role_producer_matches_kind",
            ),
            models.CheckConstraint(
                condition=(
                    Q(kind="custom", code__isnull=True)
                    | (~Q(kind="custom") & Q(code__isnull=False))
                ),
                name="accounts_role_code_matches_kind",
            ),
        ]
        permissions = [
            ("roles_view", "Puede consultar roles y el catálogo de permisos"),
            ("roles_manage", "Puede crear, editar y borrar roles propios"),
        ]
        ordering = ["name", "id"]

    def __str__(self):
        return self.name

    @property
    def permission_names(self) -> dict[str, str]:
        """Cada permiso del rol con su nombre legible, en la misma forma "app_label.codename" que
        `has_perm`."""
        return {
            f"{permission.content_type.app_label}.{permission.codename}": permission.name
            for permission in self.group.permissions.all()
        }

    @property
    def permission_codes(self) -> frozenset[str]:
        """Los permisos del rol, en la misma forma "app_label.codename" que `has_perm`."""
        return frozenset(self.permission_names)


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


class AccountManagementEvent(models.Model):
    """Auditoría mínima de HU-03: sin texto libre, nunca datos personales."""

    class EventType(models.TextChoices):
        ACCOUNT_CREATED = "account_created", "Cuenta creada"
        ACCOUNT_ACTIVATED = "account_activated", "Cuenta activada"
        ACCOUNT_DEACTIVATED = "account_deactivated", "Cuenta desactivada"
        ACCOUNT_REACTIVATED = "account_reactivated", "Cuenta reactivada"
        ACCOUNT_DELETED = "account_deleted", "Cuenta eliminada"
        ACCOUNT_ROLES_CHANGED = "account_roles_changed", "Roles de la cuenta cambiados"
        ROLE_CREATED = "role_created", "Rol creado"
        ROLE_UPDATED = "role_updated", "Rol actualizado"
        ROLE_DELETED = "role_deleted", "Rol borrado"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event_type = models.CharField(max_length=32, choices=EventType.choices)
    actor = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    target_user = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    # Sin FK: un rol borrado no debe borrar en cascada (ni bloquear el borrado por) su propio
    # historial de auditoría.
    target_role_id = models.UUIDField(null=True, blank=True)
    # Sin FK: la cuenta eliminada ya no existe, y su rastro debe sobrevivirla sin sus datos.
    target_user_ref = models.UUIDField(null=True, blank=True)
    request_id = models.UUIDField(default=uuid.uuid4, editable=False)
    occurred_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-occurred_at"]
