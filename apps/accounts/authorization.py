from django.contrib.auth.models import Permission
from rest_framework.exceptions import ValidationError

from .access import is_association_admin
from .exceptions import (
    ExceedsOwnPermissions,
    LastAdministrator,
    RoleImmutable,
    SelfModification,
    SelfRoleLockout,
)
from .models import Role, User
from .registry import is_delegable
from .scope import acts_for_producer
from .system_roles import ADMINISTRATOR, PRODUCER

ROLES_MANAGE = "accounts.roles_manage"

# Con qué rol nace cada clase de cuenta (HU-03): condiciona qué puede asignarse y quién lo hace.
ACCOUNT_KIND_ADMINISTRATOR = "administrator"
ACCOUNT_KIND_PRODUCER = "producer"
ACCOUNT_KIND_EMPLOYEE = "employee"

EXCLUSIVE_ROLE_CODES = frozenset({ADMINISTRATOR, PRODUCER})


def effective_permissions(user) -> frozenset[str]:
    """Los permisos de sus roles y los que tenga directos, en forma "app_label.codename"."""
    return frozenset(user.get_all_permissions())


def ensure_can_grant(actor, codes) -> None:
    """Regla "conceder": un rol propio solo lleva permisos delegables que el actor ya tiene."""
    if actor.is_superuser:
        return
    allowed = effective_permissions(actor)
    if any(not is_delegable(code) or code not in allowed for code in codes):
        raise ExceedsOwnPermissions("permission_codes")


def ensure_valid_role_set(roles) -> None:
    """Al menos un rol; `administrator` y `producer` son exclusivos: no se combinan con otros."""
    roles = list(roles)
    if not roles:
        raise ValidationError({"role_ids": ["Debe asignar al menos un rol."]})
    codes = {role.code for role in roles}
    if len(roles) > 1 and codes & EXCLUSIVE_ROLE_CODES:
        raise ValidationError(
            {"role_ids": ["Los roles Administrador y Productor no se combinan con otros."]}
        )


def ensure_can_assign_roles(actor, roles, *, target_producer_id, account_kind) -> None:
    """Regla "asignar": solo roles cuyos permisos el actor ya tiene, dentro de su alcance.

    `administrator` y `producer` solo los asigna quien tiene el rol Administrador, y solo al
    crear una cuenta de esa misma clase (`account_kind`).
    """
    if actor.is_superuser:
        return
    roles = list(roles)
    codes = {role.code for role in roles}

    if account_kind in (ACCOUNT_KIND_ADMINISTRATOR, ACCOUNT_KIND_PRODUCER):
        expected = {ADMINISTRATOR if account_kind == ACCOUNT_KIND_ADMINISTRATOR else PRODUCER}
        if codes != expected or not is_association_admin(actor):
            raise ExceedsOwnPermissions("role_ids")
        return

    if codes & EXCLUSIVE_ROLE_CODES:
        raise ExceedsOwnPermissions("role_ids")
    if not acts_for_producer(actor, target_producer_id):
        raise ExceedsOwnPermissions("role_ids")

    allowed = effective_permissions(actor)
    for role in roles:
        if role.producer_id not in (None, target_producer_id):
            raise ExceedsOwnPermissions("role_ids")
        if not role.permission_codes <= allowed:
            raise ExceedsOwnPermissions("role_ids")


def ensure_can_manage_account(actor, target) -> None:
    """Regla "administrar": solo cuentas del mismo productor cuyos permisos ya tiene.

    El Administrador siempre alcanza la cuenta Productor y las de otros Administradores
    (`visible_users` ya las trata como siempre visibles), tenga o no sus permisos; para las
    demás cuentas depende del interruptor de la asociación (`acts_for_producer`).
    """
    if actor.is_superuser:
        return
    if is_association_admin(actor):
        if target.groups.filter(role__code__in=(ADMINISTRATOR, PRODUCER)).exists():
            return
        if not acts_for_producer(actor, target.producer_id):
            raise ExceedsOwnPermissions()
        return
    if actor.producer_id is None or actor.producer_id != target.producer_id:
        raise ExceedsOwnPermissions()
    if not effective_permissions(target) <= effective_permissions(actor):
        raise ExceedsOwnPermissions()


def ensure_can_manage_role(actor, role) -> None:
    """Un rol fijo o predefinido no se toca; uno propio, solo dentro del alcance del actor."""
    if role.kind != Role.Kind.CUSTOM:
        raise RoleImmutable()
    if actor.is_superuser:
        return
    if is_association_admin(actor):
        if not acts_for_producer(actor, role.producer_id):
            raise ExceedsOwnPermissions()
        return
    if actor.producer_id != role.producer_id:
        raise ExceedsOwnPermissions()
    if not role.permission_codes <= effective_permissions(actor):
        raise ExceedsOwnPermissions()


def ensure_role_edit_keeps_your_role_management(actor, role, new_codes) -> None:
    """Editar el rol que tú mismo tienes no te puede dejar sin `roles_manage`.

    Sin esto, quien edita el único rol que le da ese permiso puede quitárselo sin querer y
    quedar sin ningún camino para revertirlo — el mismo callejón sin salida que
    `ensure_not_last_administrator` evita para las cuentas Administrador, pero a nivel de un
    rol propio. Una edición seria (agregar un permiso, cambiar el nombre) sigue permitida
    incluso sobre el propio rol; lo único que se bloquea es perder `roles_manage` sin que
    otro de tus roles ya lo cubra.
    """
    if actor.is_superuser or ROLES_MANAGE in new_codes:
        return
    if not actor.groups.filter(pk=role.group_id).exists():
        return
    still_covered = Permission.objects.filter(
        group__in=actor.groups.exclude(pk=role.group_id),
        content_type__app_label="accounts",
        codename="roles_manage",
    ).exists()
    if not still_covered:
        raise SelfRoleLockout()


def ensure_not_self(actor, target) -> None:
    if actor.pk == target.pk:
        raise SelfModification()


def ensure_not_last_administrator(target) -> None:
    """Bloquea las cuentas de Administrador activas y rechaza si `target` es la única.

    Bloquea el conjunto completo, no solo "alguna otra": si dos desactivaciones concurrentes
    bloquearan filas distintas (la del otro administrador cada una), ninguna vería a la otra en
    curso y las dos pasarían. Al bloquear siempre las mismas filas, la segunda espera a que la
    primera termine y recalcula sobre el estado ya actualizado.

    Quien llama decide cuándo hace falta (solo si `target` tiene o va a perder el rol
    Administrador): comprobarlo siempre sería un bloqueo de fila en cada escritura de cuenta.
    """
    # of=("self",): el filtro atraviesa Group y Role (groups__role__code), y un FOR UPDATE sin
    # acotar bloquearía también esas filas compartidas por cualquier cuenta Administrador — dos
    # desactivaciones concurrentes podrían bloquearlas en órdenes distintas y producir un
    # interbloqueo real de Postgres. Solo hace falta bloquear las filas de User.
    # order_by("pk"): mismo orden de bloqueo siempre, para que dos llamadas concurrentes que
    # bloquean el mismo conjunto lo hagan en la misma secuencia y ninguna espere a la otra en
    # sentido contrario.
    administrators = (
        User.objects.select_for_update(of=("self",))
        .filter(groups__role__code=ADMINISTRATOR, is_active=True)
        .order_by("pk")
    )
    remaining = [admin for admin in administrators if admin.pk != target.pk]
    if not remaining:
        raise LastAdministrator()
