"""Ciclo de vida de una cuenta: activarla o desactivarla, reactivarla con su productor, eliminar la
creada por error y reenviar su enlace de activación."""

import uuid

from django.db import transaction
from django.db.models import ProtectedError
from rest_framework.exceptions import PermissionDenied

from apps.common.contracts.producer_reactivation import reactivate_producer

from ..access import is_association_admin
from ..auth.services import revoke_all_sessions
from ..authorization import ensure_not_last_administrator
from ..events import record_account_event
from ..exceptions import AccountHasActivity, AccountNotFound, NotActivationPending
from ..models import AccountManagementEvent, User
from ..system_roles import PRODUCER
from .activation import send_activation
from .services import is_producer_account, managed_account

# El permiso con que se cambia el estado de un productor (HU-02); esta app no importa la de
# productores, así que se nombra aquí.
PRODUCER_STATUS_PERMISSION = "producers.change_status"


def set_account_status(actor, user_id, status: str, request_id) -> User:
    """Activa o desactiva una cuenta. Reactivar la cuenta Productor de un productor inactivo
    reactiva también al productor: es la misma persona, y sin él la cuenta seguiría sin acceso.
    Por eso pide además el permiso de cambiar el estado de productores, y lo hace aunque la cuenta
    ya estuviera activa. La cuenta de un empleado no reactiva a su productor."""
    user = managed_account(actor, user_id)

    is_active = status == "active"
    reactivates_producer = (
        is_active
        and user.producer_id is not None
        and user.producer.status != "active"
        and is_producer_account(user)
    )
    if user.is_active == is_active and not reactivates_producer:
        return user
    if reactivates_producer and not actor.has_perm(PRODUCER_STATUS_PERMISSION):
        raise PermissionDenied()

    with transaction.atomic():
        # Primero el productor y después la cuenta: el mismo orden en que bloquea reactivar el
        # productor, para no interbloquearse si las dos coinciden.
        if reactivates_producer:
            reactivate_producer(user.producer_id)
        # ensure_not_last_administrator() bloquea primero: su consulta ya incluye la fila de
        # `user` (antes de excluirlo en Python). Bloquearla aparte antes, como aquí mismo se
        # hacía, y solo después el conjunto completo, deja a dos desactivaciones cruzadas
        # bloqueando en orden opuesto — un interbloqueo real de Postgres, no solo una espera.
        if not is_active and is_association_admin(user):
            ensure_not_last_administrator(user)
        locked = User.objects.select_for_update(of=("self",)).get(pk=user.pk)
        if locked.is_active == is_active:
            return locked
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


def reactivate_with_producer(producer_id, actor) -> None:
    """Reactiva la cuenta Productor cuando se reactiva su productor (registrado en el `ready()`),
    a nombre de `actor`. Corre dentro de la transacción del productor, que ya lo bloqueó. Las
    cuentas de los empleados no cambian: el estado efectivo les devuelve el acceso."""
    account = (
        User.objects.select_for_update(of=("self",))
        .filter(producer_id=producer_id, groups__role__code=PRODUCER)
        .first()
    )
    if account is None or account.is_active:
        return
    account.is_active = True
    account.save(update_fields=["is_active"])
    record_account_event(
        AccountManagementEvent.EventType.ACCOUNT_REACTIVATED,
        uuid.uuid4(),
        actor=actor,
        target_user=account,
    )


def delete_account(actor, user_id, request_id) -> None:
    """Elimina una cuenta creada por error: una que nunca inició sesión. La que ya entró se
    desactiva. Sus historiales se conservan con el actor en nulo y el evento guarda solo el id."""
    user = managed_account(actor, user_id)

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
    user = managed_account(actor, user_id, allow_self=True)
    if user.has_usable_password():
        raise NotActivationPending()
    return send_activation(user)
