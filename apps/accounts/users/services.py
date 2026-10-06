import uuid
from typing import NamedTuple

from django.contrib.auth.models import Group
from django.db import IntegrityError, transaction
from django.db.models import Prefetch, ProtectedError, QuerySet
from rest_framework.exceptions import ValidationError

from apps.common.validators import strip_document_separators

from ..access import get_producer_model, is_association_admin
from ..auth.services import revoke_all_sessions
from ..authorization import (
    ACCOUNT_KIND_ADMINISTRATOR,
    ACCOUNT_KIND_EMPLOYEE,
    ACCOUNT_KIND_PRODUCER,
    ensure_can_assign_roles,
    ensure_can_manage_account,
    ensure_not_last_administrator,
    ensure_not_self,
    ensure_valid_role_set,
)
from ..events import record_account_event
from ..exceptions import (
    AccountHasActivity,
    AccountNotFound,
    AdministratorAlreadyExists,
    DuplicateAccountDocument,
    DuplicateEmail,
    NotActivationPending,
    ProducerAlreadyLinked,
    ProducerInactive,
)
from ..models import (
    DOCUMENT_UNIQUE_CONSTRAINT,
    EMAIL_UNIQUE_CONSTRAINT,
    AccountManagementEvent,
    User,
)
from ..scope import visible_roles, visible_users
from ..system_roles import ADMINISTRATOR, PRODUCER, get_system_role
from .activation import send_activation

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


def _forbid(data: dict, *fields: str, message: str = "Campo no permitido.") -> None:
    present = [field for field in fields if field in data]
    if present:
        raise ValidationError({field: [message] for field in present})


def _resolve_account_kind(codes: set) -> str:
    if PRODUCER in codes:
        return ACCOUNT_KIND_PRODUCER
    if ADMINISTRATOR in codes:
        return ACCOUNT_KIND_ADMINISTRATOR
    return ACCOUNT_KIND_EMPLOYEE


def _build_producer_account(producer, *, email: str, phone=None) -> User:
    """Una cuenta con el documento y los nombres copiados del expediente, sin guardar
    todavía: el llamador decide cuándo (`full_clean()`, guardar, asignar el rol)."""
    return User(
        email=email,
        document_type=producer.document_type,
        identity_document=producer.identity_document,
        first_name=producer.first_name,
        last_name=producer.last_name,
        phone=phone,
        producer_id=producer.id,
    )


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


def _save_new_account(user: User) -> None:
    """Deja la cuenta sin contraseña (se activa por correo) y la guarda ya validada."""
    user.set_unusable_password()
    # full_clean() normaliza correo y documento y corre los validadores del modelo (formato de
    # documento, teléfono): un DjangoValidationError sin campo propio ya lo traduce el manejador
    # global de errores a `validation_error`.
    user.full_clean(validate_unique=False, validate_constraints=False)
    _save_or_raise_duplicate(user)


def _resolve_roles(actor, role_ids) -> list:
    roles = list(visible_roles(actor).filter(pk__in=role_ids))
    if len(roles) != len(set(role_ids)):
        # Un id que no está al alcance de quien actúa se trata como si no existiera.
        raise ValidationError({"role_ids": ["Alguno de los roles no existe."]})
    ensure_valid_role_set(roles)
    return roles


def _managed_account(actor, user_id, *, allow_self: bool = False) -> User:
    """La cuenta que `actor` puede administrar; sin `allow_self`, tampoco la suya."""
    user = get_account(actor, user_id)
    if not allow_self:
        ensure_not_self(actor, user)
    ensure_can_manage_account(actor, user)
    return user


def create_account(actor, data: dict, request_id) -> CreatedAccount:
    roles = _resolve_roles(actor, data["role_ids"])

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
            user = _build_producer_account(producer, email=data["email"], phone=data.get("phone"))
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
        _save_new_account(user)
        user.groups.set(role.group for role in roles)
        record_account_event(
            AccountManagementEvent.EventType.ACCOUNT_CREATED,
            request_id,
            actor=actor,
            target_user=user,
        )

    activation_email_sent = send_activation(user)
    return CreatedAccount(user=user, activation_email_sent=activation_email_sent)


def update_account(actor, user_id, data: dict, request_id) -> User:
    user = _managed_account(actor, user_id)

    if user.groups.filter(role__code=PRODUCER).exists():
        _forbid(data, *PERSONAL_FIELDS, message="Lo gobierna el expediente del productor.")
    if "identity_document" in data:
        # Mismo motivo que en create_account: normalizar antes de full_clean().
        data["identity_document"] = strip_document_separators(data["identity_document"])

    email_changed = "email" in data and data["email"] != user.email

    with transaction.atomic():
        for field, value in data.items():
            setattr(user, field, value)
        user.full_clean(validate_unique=False, validate_constraints=False)
        _save_or_raise_duplicate(user)
        if email_changed:
            # Un correo nuevo también sirve para iniciar sesión; las sesiones abiertas con el
            # anterior no deben seguir sirviendo.
            revoke_all_sessions(user)
    return user


def set_account_roles(actor, user_id, role_ids, request_id) -> User:
    user = _managed_account(actor, user_id)

    if user.groups.filter(role__code__in=(ADMINISTRATOR, PRODUCER)).exists():
        raise ValidationError({"role_ids": ["Esta cuenta no cambia de rol por aquí."]})

    roles = _resolve_roles(actor, role_ids)
    ensure_can_assign_roles(
        actor, roles, target_producer_id=user.producer_id, account_kind=ACCOUNT_KIND_EMPLOYEE
    )

    with transaction.atomic():
        user.groups.set(role.group for role in roles)
        record_account_event(
            AccountManagementEvent.EventType.ACCOUNT_ROLES_CHANGED,
            request_id,
            actor=actor,
            target_user=user,
        )
    return user


def set_account_status(actor, user_id, status: str, request_id) -> User:
    user = _managed_account(actor, user_id)

    is_active = status == "active"
    if user.is_active == is_active:
        return user

    with transaction.atomic():
        # ensure_not_last_administrator() bloquea primero: su consulta ya incluye la fila de
        # `user` (antes de excluirlo en Python). Bloquearla aparte antes, como aquí mismo se
        # hacía, y solo después el conjunto completo, deja a dos desactivaciones cruzadas
        # bloqueando en orden opuesto — un interbloqueo real de Postgres, no solo una espera.
        if not is_active and is_association_admin(user):
            ensure_not_last_administrator(user)
        locked = User.objects.select_for_update(of=("self",)).get(pk=user.pk)
        locked.is_active = is_active
        locked.save(update_fields=["is_active"])
        if not is_active:
            revoke_all_sessions(locked)
        record_account_event(
            (
                AccountManagementEvent.EventType.ACCOUNT_DEACTIVATED
                if not is_active
                else AccountManagementEvent.EventType.ACCOUNT_REACTIVATED
            ),
            request_id,
            actor=actor,
            target_user=locked,
        )
    return locked


def delete_account(actor, user_id, request_id) -> None:
    """Elimina una cuenta creada por error: una que nunca inició sesión. La que ya entró se
    desactiva. Sus historiales se conservan con el actor en nulo y el evento guarda solo el id."""
    user = _managed_account(actor, user_id)

    with transaction.atomic():
        # Mismo orden de bloqueo que `set_account_status`: primero el del conjunto de
        # administradores y solo después la fila de la cuenta.
        if is_association_admin(user):
            ensure_not_last_administrator(user)
        locked = User.objects.select_for_update(of=("self",)).filter(pk=user.pk).first()
        # Otra solicitud pudo eliminarla mientras se esperaba el bloqueo.
        if locked is None:
            raise AccountNotFound()
        # Con la fila bloqueada: un inicio de sesión que llega a la vez espera aquí.
        if locked.last_login is not None:
            raise AccountHasActivity()
        user_ref = locked.pk
        try:
            with transaction.atomic():
                locked.delete()
        except ProtectedError:
            raise AccountHasActivity() from None
        record_account_event(
            AccountManagementEvent.EventType.ACCOUNT_DELETED,
            request_id,
            actor=actor,
            target_user_ref=user_ref,
        )


def resend_activation(actor, user_id) -> bool:
    user = _managed_account(actor, user_id, allow_self=True)
    if user.has_usable_password():
        raise NotActivationPending()
    return send_activation(user)


def create_producer_account_automatically(producer) -> None:
    """Crea la cuenta Productor al registrar el expediente (HU-02+HU-03).

    Sin actor: es una reacción del sistema a `Producer.save()` (ver `apps.py`), no una acción
    de alguien autenticado. Si el correo o el documento ya pertenecen a otra cuenta, no se crea
    nada; como esto corre dentro de la misma transacción que `create_producer()`, también
    revierte el alta del productor.

    El correo es obligatorio en la API (ver `producers/serializers.py`), pero el campo del
    modelo sigue siendo opcional para datos ajenos a ella (admin, scripts, una migración):
    un productor guardado sin correo simplemente no recibe cuenta todavía.
    """
    if not producer.email:
        return
    role = get_system_role(PRODUCER)
    user = _build_producer_account(producer, email=producer.email)
    _save_new_account(user)
    user.groups.set([role.group])
    record_account_event(
        AccountManagementEvent.EventType.ACCOUNT_CREATED,
        uuid.uuid4(),
        target_user=user,
    )
    transaction.on_commit(lambda: send_activation(user))


def create_first_administrator(data: dict) -> User:
    """Crea la cuenta Administrador inicial (comando de despliegue, sin actor autenticado).

    Se niega si ya existe una cuenta con el rol Administrador: HU-03 no tiene un flujo para
    reemplazar al primero, y crear uno nuevo por aquí saltaría esa decisión.
    """
    if User.objects.filter(groups__role__code=ADMINISTRATOR).exists():
        raise AdministratorAlreadyExists()

    role = get_system_role(ADMINISTRATOR)
    user = User(
        email=data["email"],
        document_type=data["document_type"],
        identity_document=data["identity_document"],
        first_name=data["first_name"],
        last_name=data["last_name"],
    )
    with transaction.atomic():
        _save_new_account(user)
        user.groups.set([role.group])
        record_account_event(
            AccountManagementEvent.EventType.ACCOUNT_CREATED,
            uuid.uuid4(),
            target_user=user,
        )
    send_activation(user)
    return user
