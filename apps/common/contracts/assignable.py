"""Quién puede responder por una labor en una finca: la regla que comparten los responsables de
una actividad y los recolectores de una cosecha. Solo cambia el permiso que cada labor exige.

Una cuenta puede responder si está activa, es del productor de la finca, tiene el permiso de la
labor y, si es un empleado, trabaja en esa finca (o en todas). Se decide por el permiso y no por
el nombre del rol, que en un rol propio puede ser cualquiera.
"""

from collections.abc import Callable

from django.contrib.auth import get_user_model

from ..ownership import reaches_all_farms
from ..roles import is_employee


def person_options(
    actor, producer_id, permission: str, *, producer_required: Callable[[], Exception]
) -> list[dict]:
    """Las cuentas del productor que `actor` alcanza (su cuenta y sus empleados), activas e
    inactivas, con lo necesario para decidir a quién asignarle una labor. Las inactivas sirven
    para filtrar y para mostrar labores viejas; el formulario solo ofrece las activas.

    Un empleado recibe a la gente que comparte alguna finca con él y al Productor. De cada cuenta,
    las fincas en las que trabaja (`farm_ids`, vacía en el Productor, que vale para todas) y si
    `actor` puede asignarle (`assignable`): con eso el formulario arma la lista de la parcela
    elegida, también sin conexión. No lleva el documento ni los roles: quien asigna no tiene por
    qué verlos. Una cuenta sin nombre se muestra por su correo, como en los historiales: es la
    única forma de reconocerla. La cuenta técnica dice de qué productor; de cualquier otra cuenta
    `producer_id` se ignora.
    """
    if actor.is_superuser:
        if producer_id is None:
            raise producer_required()
    else:
        producer_id = actor.producer_id
    if producer_id is None:
        return []
    accounts = (
        get_user_model()
        .objects.filter(producer_id=producer_id, is_superuser=False)
        .prefetch_related("farms")
        .order_by("last_name", "first_name", "id")
    )
    actor_farms = None if reaches_all_farms(actor) else _farm_ids(actor)
    options = []
    for account in accounts:
        employee = is_employee(account)
        # El Productor y quien trabaja en todas valen para cualquier finca: sin lista.
        all_farms = not employee or account.all_farms
        farm_ids = [] if all_farms else sorted(_farm_ids(account), key=str)
        if actor_farms is not None and not all_farms and not actor_farms & set(farm_ids):
            continue
        options.append(
            {
                "id": account.pk,
                "full_name": account.get_full_name() or account.email,
                "is_active": account.is_active,
                "farm_ids": farm_ids,
                "all_farms": all_farms,
                "assignable": _takes_work(actor, account, employee, permission),
            }
        )
    return options


def assignable_person(actor, plot, account_id, permission: str):
    """La cuenta, si `actor` puede hacerla responsable de una labor en `plot`, o `None`. Nunca una
    cuenta técnica ni de la asociación, que no tienen productor."""
    account = (
        get_user_model()
        .objects.filter(
            pk=account_id, producer_id=plot.farm.producer_id, is_active=True, is_superuser=False
        )
        .first()
    )
    if account is None:
        return None
    employee = is_employee(account)
    if employee and not account.all_farms and plot.farm_id not in _farm_ids(account):
        return None
    return account if _takes_work(actor, account, employee, permission) else None


def _farm_ids(account) -> set:
    # Con `.all()`, para aprovechar las fincas precargadas de una lista.
    return {farm.pk for farm in account.farms.all()}


def _takes_work(actor, account, employee: bool, permission: str) -> bool:
    """Si a `account` se le puede asignar una labor y `actor` puede hacerlo.

    A quien se le asigna una labor debe poder registrarla: por eso decide el permiso de la labor.
    Un empleado sin finca no trabaja en ninguna. Al Productor solo le asigna él mismo (o la cuenta
    técnica): un empleado no le pone labores a quien lo dirige.
    """
    if not account.has_perm(permission):
        return False
    if employee:
        return account.all_farms or bool(_farm_ids(account))
    return not is_employee(actor)
