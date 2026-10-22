"""Alta de cuentas: la que crea quien administra, la cuenta Productor que nace con su productor y
el primer Administrador de la asociación."""

import uuid
from typing import NamedTuple

from django.db import transaction
from rest_framework.exceptions import ValidationError

from apps.common.validators import strip_document_separators

from ..access import get_producer_model, is_association_admin
from ..authorization import (
    ACCOUNT_KIND_ADMINISTRATOR,
    ACCOUNT_KIND_EMPLOYEE,
    ACCOUNT_KIND_PRODUCER,
    ensure_can_assign_roles,
)
from ..events import record_account_event
from ..exceptions import AdministratorAlreadyExists, ProducerAlreadyLinked, ProducerInactive
from ..models import AccountManagementEvent, User
from ..system_roles import ADMINISTRATOR, PRODUCER, get_system_role
from .activation import send_activation
from .farm_assignment import scope_for_new_account
from .services import (
    PERSONAL_FIELDS,
    forbid_fields,
    require_fields,
    resolve_roles,
    save_or_raise_duplicate,
)


class CreatedAccount(NamedTuple):
    user: User
    activation_email_sent: bool


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


def _save_new_account(user: User) -> None:
    """Deja la cuenta sin contraseña (se activa por correo) y la guarda ya validada."""
    user.set_unusable_password()
    # full_clean() normaliza correo y documento y corre los validadores del modelo (formato de
    # documento, teléfono): un DjangoValidationError sin campo propio ya lo traduce el manejador
    # global de errores a `validation_error`.
    user.full_clean(validate_unique=False, validate_constraints=False)
    save_or_raise_duplicate(user)


def create_account(actor, data: dict, request_id) -> CreatedAccount:
    roles = resolve_roles(actor, data["role_ids"])

    account_kind = _resolve_account_kind({role.code for role in roles})
    producer_id = data.get("producer_id")

    if account_kind == ACCOUNT_KIND_ADMINISTRATOR:
        forbid_fields(data, "producer_id", "farm_ids", "all_farms")
        require_fields(data, *PERSONAL_FIELDS)
        target_producer_id = None
    elif account_kind == ACCOUNT_KIND_PRODUCER:
        require_fields(data, "producer_id")
        forbid_fields(data, *PERSONAL_FIELDS, "farm_ids", "all_farms")
        target_producer_id = producer_id
    else:
        if is_association_admin(actor) or actor.is_superuser:
            require_fields(data, "producer_id")
            target_producer_id = producer_id
        else:
            forbid_fields(data, "producer_id")
            target_producer_id = actor.producer_id
            if target_producer_id is None:
                raise ValidationError(
                    {"producer_id": ["Tu cuenta no pertenece a ningún productor."]}
                )
        require_fields(data, *PERSONAL_FIELDS)

    if account_kind != ACCOUNT_KIND_PRODUCER:
        # Antes de construir la instancia: full_clean() valida max_length sobre el valor
        # crudo antes de que User.clean() le quite los separadores, y uno con puntos o
        # guiones puede superarlo aunque tenga 15 dígitos o menos.
        data["identity_document"] = strip_document_separators(data["identity_document"])

    ensure_can_assign_roles(
        actor, roles, target_producer_id=target_producer_id, account_kind=account_kind
    )
    all_farms, farms = (
        scope_for_new_account(
            actor, target_producer_id, roles, data.get("farm_ids"), bool(data.get("all_farms"))
        )
        if account_kind == ACCOUNT_KIND_EMPLOYEE
        else (False, [])
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
                all_farms=all_farms,
            )
        _save_new_account(user)
        user.farms.set(farms)
        user.groups.set(role.group for role in roles)
        record_account_event(
            AccountManagementEvent.EventType.ACCOUNT_CREATED,
            request_id,
            actor=actor,
            target_user=user,
        )

    activation_email_sent = send_activation(user)
    return CreatedAccount(user=user, activation_email_sent=activation_email_sent)


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
