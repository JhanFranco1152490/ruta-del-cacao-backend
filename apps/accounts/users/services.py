"""Consultar y editar cuentas: sus datos, sus roles y las fincas en las que trabaja. El alta está
en `creation` y el ciclo de vida (estado, eliminar, reenviar la activación) en `lifecycle`."""

from django.contrib.auth.models import Group
from django.db import IntegrityError, transaction
from django.db.models import Prefetch, QuerySet
from rest_framework.exceptions import ValidationError

from apps.common.validators import strip_document_separators

from ..access import roles_of
from ..auth.services import revoke_all_sessions
from ..authorization import (
    ACCOUNT_KIND_EMPLOYEE,
    ensure_can_assign_roles,
    ensure_can_manage_account,
    ensure_not_self,
    ensure_valid_role_set,
)
from ..events import record_account_event
from ..exceptions import AccountNotFound, DuplicateAccountDocument, DuplicateEmail
from ..models import (
    DOCUMENT_UNIQUE_CONSTRAINT,
    EMAIL_UNIQUE_CONSTRAINT,
    AccountManagementEvent,
    User,
)
from ..scope import visible_roles, visible_users
from ..system_roles import ADMINISTRATOR, PRODUCER
from .farm_assignment import change_scope, keeps_scope_for

# El alcance no se envió: distinto de enviarlo vacío, que lo quita.
SCOPE_NOT_SENT = object()


PERSONAL_FIELDS = ("document_type", "identity_document", "first_name", "last_name")


# Nombre que Django genera solo, para el `unique=True` de `EmailField` (previo a HU-03, sensible
# a mayúsculas); se suma a EMAIL_UNIQUE_CONSTRAINT porque un correo repetido puede violar
# cualquiera de las dos restricciones únicas de la columna.
IMPLICIT_EMAIL_UNIQUE_CONSTRAINT = "accounts_user_email_key"


def _optimized(queryset: QuerySet) -> QuerySet:
    """`select_related`/`prefetch_related` para servir cuentas sin una consulta por fila."""
    # Los permisos de cada rol también: con ellos se sabe si a la cuenta le falta la finca.
    return queryset.select_related("producer").prefetch_related(
        "farms",
        Prefetch(
            "groups",
            queryset=Group.objects.select_related("role").prefetch_related(
                "permissions__content_type"
            ),
        ),
    )


def get_account(actor, user_id) -> User:
    user = _optimized(visible_users(actor)).filter(pk=user_id).first()
    if user is None:
        raise AccountNotFound()
    return user


def list_accounts(actor) -> QuerySet:
    return _optimized(visible_users(actor))


def require_fields(data: dict, *fields: str) -> None:
    missing = [field for field in fields if field not in data]
    if missing:
        raise ValidationError({field: ["Este campo es requerido."] for field in missing})


def forbid_fields(data: dict, *fields: str, message: str = "Campo no permitido.") -> None:
    present = [field for field in fields if field in data]
    if present:
        raise ValidationError({field: [message] for field in present})


def save_or_raise_duplicate(user: User) -> None:
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


def resolve_roles(actor, role_ids) -> list:
    roles = list(visible_roles(actor).filter(pk__in=role_ids))
    if len(roles) != len(set(role_ids)):
        # Un id que no está al alcance de quien actúa se trata como si no existiera.
        raise ValidationError({"role_ids": ["Alguno de los roles no existe."]})
    ensure_valid_role_set(roles)
    return roles


def managed_account(actor, user_id, *, allow_self: bool = False) -> User:
    """La cuenta que `actor` puede administrar; sin `allow_self`, tampoco la suya."""
    user = get_account(actor, user_id)
    if not allow_self:
        ensure_not_self(actor, user)
    ensure_can_manage_account(actor, user)
    return user


def is_producer_account(user) -> bool:
    return user.groups.filter(role__code=PRODUCER).exists()


def update_account(actor, user_id, data: dict, request_id) -> User:
    user = managed_account(actor, user_id)

    if is_producer_account(user):
        forbid_fields(data, *PERSONAL_FIELDS, message="Lo gobierna el expediente del productor.")
    if "identity_document" in data:
        # Mismo motivo que en create_account: normalizar antes de full_clean().
        data["identity_document"] = strip_document_separators(data["identity_document"])

    email_changed = "email" in data and data["email"] != user.email
    new_scope = _scope_change(actor, user, roles_of(user), data)

    with transaction.atomic():
        for field, value in data.items():
            setattr(user, field, value)
        user.full_clean(validate_unique=False, validate_constraints=False)
        save_or_raise_duplicate(user)
        if email_changed:
            # Un correo nuevo también sirve para iniciar sesión; las sesiones abiertas con el
            # anterior no deben seguir sirviendo.
            revoke_all_sessions(user)
        _apply_scope(actor, user, new_scope, request_id)
    return user


def _scope_change(actor, user, roles, data: dict):
    """El alcance nuevo si la petición trae `farm_ids` o `all_farms` (los quita de `data`), o
    `None` si no lo toca o queda igual. Enviar solo uno de los dos deja el otro como «no»."""
    if "farm_ids" not in data and "all_farms" not in data:
        return None
    farm_ids = data.pop("farm_ids", None)
    all_farms = bool(data.pop("all_farms", False))
    return change_scope(actor, user, roles, farm_ids, all_farms)


def _apply_scope(actor, user: User, new_scope, request_id) -> None:
    if new_scope is None:
        return
    all_farms, farms = new_scope
    if user.all_farms != all_farms:
        user.all_farms = all_farms
        user.save(update_fields=["all_farms"])
    user.farms.set(farms)
    _record_farm_change(actor, user, request_id)


def set_account_roles(
    actor, user_id, role_ids, request_id, farm_ids=SCOPE_NOT_SENT, all_farms=SCOPE_NOT_SENT
) -> User:
    """Reemplaza los roles de un empleado. `farm_ids` y `all_farms` dejan dar el alcance en la
    misma operación en que los roles nuevos lo exigen: sin alcance no alcanzarían nada."""
    user = managed_account(actor, user_id)

    if user.groups.filter(role__code__in=(ADMINISTRATOR, PRODUCER)).exists():
        raise ValidationError({"role_ids": ["Esta cuenta no cambia de rol por aquí."]})

    roles = resolve_roles(actor, role_ids)
    ensure_can_assign_roles(
        actor, roles, target_producer_id=user.producer_id, account_kind=ACCOUNT_KIND_EMPLOYEE
    )
    if farm_ids is SCOPE_NOT_SENT and all_farms is SCOPE_NOT_SENT:
        # Sin enviarlo, el alcance que ya tiene debe cumplir lo que piden los roles nuevos.
        keeps_scope_for(roles, user)
        new_scope = None
    else:
        new_scope = change_scope(
            actor,
            user,
            roles,
            None if farm_ids is SCOPE_NOT_SENT else farm_ids,
            False if all_farms is SCOPE_NOT_SENT else bool(all_farms),
        )

    with transaction.atomic():
        user.groups.set(role.group for role in roles)
        record_account_event(
            AccountManagementEvent.EventType.ACCOUNT_ROLES_CHANGED,
            request_id,
            actor=actor,
            target_user=user,
        )
        _apply_scope(actor, user, new_scope, request_id)
    return user


def _record_farm_change(actor, user: User, request_id) -> None:
    record_account_event(
        AccountManagementEvent.EventType.ACCOUNT_FARM_CHANGED,
        request_id,
        actor=actor,
        target_user=user,
    )
