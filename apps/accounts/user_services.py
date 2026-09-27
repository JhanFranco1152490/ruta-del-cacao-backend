from typing import NamedTuple

from django.contrib.auth.models import Group
from django.db import IntegrityError, transaction
from django.db.models import Prefetch, QuerySet
from rest_framework.exceptions import ValidationError

from apps.common.validators import strip_document_separators

from .access import get_producer_model, is_association_admin
from .activation import send_activation
from .authorization import (
    ACCOUNT_KIND_ADMINISTRATOR,
    ACCOUNT_KIND_EMPLOYEE,
    ACCOUNT_KIND_PRODUCER,
    ensure_can_assign_roles,
    ensure_valid_role_set,
)
from .events import record_account_event
from .exceptions import (
    AccountNotFound,
    DuplicateAccountDocument,
    DuplicateEmail,
    ProducerAlreadyLinked,
    ProducerInactive,
)
from .models import (
    DOCUMENT_UNIQUE_CONSTRAINT,
    EMAIL_UNIQUE_CONSTRAINT,
    AccountManagementEvent,
    User,
)
from .scope import visible_roles, visible_users
from .system_roles import ADMINISTRATOR, PRODUCER

PERSONAL_FIELDS = ("document_type", "identity_document", "first_name", "last_name")
# Nombre que Django genera solo, para el `unique=True` de `EmailField` (previo a HU-03, sensible
# a mayúsculas); se suma a EMAIL_UNIQUE_CONSTRAINT porque un correo repetido puede violar
# cualquiera de las dos restricciones únicas de la columna.
IMPLICIT_EMAIL_UNIQUE_CONSTRAINT = "accounts_user_email_key"


class CreatedAccount(NamedTuple):
    user: User
    activation_email_sent: bool


def _optimized(queryset: QuerySet) -> QuerySet:
    """`select_related`/`prefetch_related` para servir cuentas sin una consulta por fila."""
    return queryset.select_related("producer").prefetch_related(
        Prefetch("groups", queryset=Group.objects.select_related("role"))
    )


def get_account(actor, user_id) -> User:
    user = _optimized(visible_users(actor)).filter(pk=user_id).first()
    if user is None:
        raise AccountNotFound()
    return user


def list_accounts(actor) -> QuerySet:
    return _optimized(visible_users(actor))


def _require(data: dict, *fields: str) -> None:
    missing = [field for field in fields if field not in data]
    if missing:
        raise ValidationError({field: ["Este campo es requerido."] for field in missing})


def _forbid(data: dict, *fields: str) -> None:
    present = [field for field in fields if field in data]
    if present:
        raise ValidationError({field: ["Campo no permitido."] for field in present})


def _resolve_account_kind(codes: set) -> str:
    if PRODUCER in codes:
        return ACCOUNT_KIND_PRODUCER
    if ADMINISTRATOR in codes:
        return ACCOUNT_KIND_ADMINISTRATOR
    return ACCOUNT_KIND_EMPLOYEE


def _lock_producer(producer_id):
    producer_model = get_producer_model()
    producer = producer_model.objects.select_for_update().filter(pk=producer_id).first()
    if producer is None:
        raise ValidationError({"producer_id": ["No existe."]})
    return producer


def _save_or_raise_duplicate(user: User) -> None:
    # El duplicado lo detecta la restricción única de la base de datos, igual que en
    # producers: es lo único que resiste dos altas simultáneas con el mismo correo o
    # documento. El savepoint deja la transacción usable para seguir tras el error.
    try:
        with transaction.atomic():
            user.save()
    except IntegrityError as error:
        constraint = getattr(getattr(error.__cause__, "diag", None), "constraint_name", None)
        if constraint in (EMAIL_UNIQUE_CONSTRAINT, IMPLICIT_EMAIL_UNIQUE_CONSTRAINT):
            raise DuplicateEmail() from None
        if constraint == DOCUMENT_UNIQUE_CONSTRAINT:
            raise DuplicateAccountDocument() from None
        raise


def create_account(actor, data: dict, request_id) -> CreatedAccount:
    role_ids = data["role_ids"]
    roles = list(visible_roles(actor).filter(pk__in=role_ids))
    if len(roles) != len(set(role_ids)):
        # Un id que no está al alcance de quien crea se trata como si no existiera.
        raise ValidationError({"role_ids": ["Alguno de los roles no existe."]})
    ensure_valid_role_set(roles)

    account_kind = _resolve_account_kind({role.code for role in roles})
    producer_id = data.get("producer_id")

    if account_kind == ACCOUNT_KIND_ADMINISTRATOR:
        _forbid(data, "producer_id")
        _require(data, *PERSONAL_FIELDS)
        target_producer_id = None
    elif account_kind == ACCOUNT_KIND_PRODUCER:
        _require(data, "producer_id")
        _forbid(data, *PERSONAL_FIELDS)
        target_producer_id = producer_id
    else:
        if is_association_admin(actor) or actor.is_superuser:
            _require(data, "producer_id")
            target_producer_id = producer_id
        else:
            _forbid(data, "producer_id")
            target_producer_id = actor.producer_id
            if target_producer_id is None:
                raise ValidationError(
                    {"producer_id": ["Tu cuenta no pertenece a ningún productor."]}
                )
        _require(data, *PERSONAL_FIELDS)

    if account_kind != ACCOUNT_KIND_PRODUCER:
        # Antes de construir la instancia: full_clean() valida max_length sobre el valor
        # crudo antes de que User.clean() le quite los separadores, y uno con puntos o
        # guiones puede superarlo aunque tenga 15 dígitos o menos.
        data["identity_document"] = strip_document_separators(data["identity_document"])

    ensure_can_assign_roles(
        actor, roles, target_producer_id=target_producer_id, account_kind=account_kind
    )

    with transaction.atomic():
        if account_kind == ACCOUNT_KIND_PRODUCER:
            producer = _lock_producer(target_producer_id)
            if producer.status != "active":
                raise ProducerInactive()
            if User.objects.filter(producer_id=producer.id, groups__role__code=PRODUCER).exists():
                raise ProducerAlreadyLinked()
            user = User(
                email=data["email"],
                document_type=producer.document_type,
                identity_document=producer.identity_document,
                first_name=producer.first_name,
                last_name=producer.last_name,
                phone=data.get("phone"),
                producer_id=producer.id,
            )
        else:
            user = User(
                email=data["email"],
                document_type=data["document_type"],
                identity_document=data["identity_document"],
                first_name=data["first_name"],
                last_name=data["last_name"],
                phone=data.get("phone"),
                producer_id=target_producer_id,
            )
        user.set_unusable_password()
        # full_clean() normaliza correo y documento y corre los validadores del modelo
        # (formato de documento, teléfono): un DjangoValidationError sin campo propio ya lo
        # traduce el manejador global de errores a `validation_error`.
        user.full_clean(validate_unique=False, validate_constraints=False)
        _save_or_raise_duplicate(user)
        user.groups.set(role.group for role in roles)
        record_account_event(
            AccountManagementEvent.EventType.ACCOUNT_CREATED,
            request_id,
            actor=actor,
            target_user=user,
        )

    activation_email_sent = send_activation(user)
    return CreatedAccount(user=user, activation_email_sent=activation_email_sent)
