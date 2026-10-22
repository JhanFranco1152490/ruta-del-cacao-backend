"""El alcance de un empleado: en qué fincas trabaja, o si trabaja en todas, quién se lo da y qué
admite cada rol.

El rol dice qué puede hacer una cuenta; el alcance dice dónde. Cada rol limita qué alcances admite
(`Role.farm_scope`: todas, una sola, una o varias) y la cuenta tiene el valor: la marca
`all_farms` o una lista de fincas. Un empleado puede trabajar en varias fincas del mismo productor
(por ejemplo, vecinas), o en todas.
"""

from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.common.contracts.farm_change_guards import PendingWork, pending_work
from apps.common.ownership import reaches_all_farms
from apps.common.roles import is_employee

from ..exceptions import AccountHasPendingWork, RoleScopeConflict
from ..models import Role, User
from ..system_roles import ADMINISTRATOR, PRODUCER

SCOPE_REQUIRED = "Indica en qué fincas trabaja o marca todas las fincas."
SCOPE_AND_FARMS = "Elige todas las fincas o fincas específicas, no las dos."
FARM_NOT_AVAILABLE = "Elige fincas activas del productor."
OWN_FARMS_ONLY = "Solo puedes crear cuentas para las fincas en las que trabajas."
CHOOSE_ONE_OF_YOURS = "Indica en cuál de tus fincas va a trabajar."
ONLY_ALL_FARMS_GIVE_ALL = "Solo quien alcanza todas las fincas puede dar todas las fincas."
ONLY_ALL_FARMS_CHANGE = "Solo quien alcanza todas las fincas cambia el alcance de un empleado."
ROLE_NEEDS_ALL = "Este rol pide todas las fincas."
ROLE_NEEDS_ONE = "Este rol pide exactamente una finca."


def scope_of_roles(roles) -> str:
    """El alcance que exigen los roles juntos: `all`, `one` o `many` (sin exigencia). Todas con una
    sola es incompatible; lo demás se resuelve solo: `all` y `one` mandan sobre `many`."""
    scopes = {role.farm_scope for role in roles}
    if {Role.FarmScope.ALL, Role.FarmScope.ONE} <= scopes:
        raise RoleScopeConflict()
    if Role.FarmScope.ALL in scopes:
        return Role.FarmScope.ALL
    if Role.FarmScope.ONE in scopes:
        return Role.FarmScope.ONE
    return Role.FarmScope.MANY


def needs_farm(user) -> bool:
    """Si a la cuenta le falta alcance: es de un empleado y no tiene fincas ni «todas». Lee las
    fincas con `.all()` para aprovechar las que ya vienen precargadas en una lista."""
    return not user.all_farms and not user.farms.all() and is_employee(user)


def employees_without_scope():
    """Los ids de los empleados sin alcance (sin fincas y sin «todas»), para filtrar un listado."""
    return (
        User.objects.filter(
            farms__isnull=True, all_farms=False, producer__isnull=False, is_superuser=False
        )
        .exclude(groups__role__code=PRODUCER)
        .values("pk")
    )


def farm_ids_of(user) -> set:
    return {farm.pk for farm in user.farms.all()} if user.pk else set()


def _farm_model():
    return User._meta.get_field("farms").related_model


def resolve_scope(
    producer_id, roles, farm_ids, all_farms, *, current=frozenset()
) -> tuple[bool, list]:
    """El alcance de una cuenta de empleado con esos roles: `(all_farms, fincas)`.

    Debe haber alguno, y cumplir lo que piden los roles. Cada finca debe ser del mismo productor y
    estar activa; las que la cuenta ya tiene (`current`) se conservan aunque se hayan desactivado.
    Una finca ajena o inexistente responde igual que una inactiva: distinguirlas confirmaría que
    existe. No comprueba quién lo da: eso es `ensure_can_give`.
    """
    wanted = set(farm_ids or ())
    if all_farms and wanted:
        raise ValidationError({"farm_ids": [SCOPE_AND_FARMS]})
    required = scope_of_roles(roles)
    if all_farms:
        if required == Role.FarmScope.ONE:
            raise ValidationError({"all_farms": [ROLE_NEEDS_ONE]})
        return True, []
    if not wanted:
        raise ValidationError({"farm_ids": [SCOPE_REQUIRED]})
    if required == Role.FarmScope.ALL:
        raise ValidationError({"all_farms": [ROLE_NEEDS_ALL]})
    if required == Role.FarmScope.ONE and len(wanted) != 1:
        raise ValidationError({"farm_ids": [ROLE_NEEDS_ONE]})
    farms = list(_farm_model().objects.filter(pk__in=wanted, producer_id=producer_id))
    if len(farms) != len(wanted) or any(
        not (farm.is_active or farm.pk in current) for farm in farms
    ):
        raise ValidationError({"farm_ids": [FARM_NOT_AVAILABLE]})
    return False, farms


def ensure_can_give(actor, all_farms, farm_ids) -> None:
    """Nadie da más alcance del que tiene: «todas las fincas» solo la da quien las alcanza todas, y
    un empleado limitado solo da fincas de las que él trabaja."""
    if reaches_all_farms(actor):
        return
    if all_farms:
        raise PermissionDenied(ONLY_ALL_FARMS_GIVE_ALL)
    if not set(farm_ids or ()) <= farm_ids_of(actor):
        raise PermissionDenied(OWN_FARMS_ONLY)


def scope_for_new_account(actor, producer_id, roles, farm_ids, all_farms) -> tuple[bool, list]:
    """El alcance de un empleado que se está creando.

    El Productor, la cuenta técnica y un empleado con «todas» eligen entre todas las fincas del
    productor. Un empleado de confianza limitado solo suma gente a las fincas en las que él
    trabaja: pedir otra, o «todas», es `403`; si no indica ninguna y trabaja en una sola, la
    cuenta nueva la toma.
    """
    ensure_can_give(actor, all_farms, farm_ids)
    if not reaches_all_farms(actor) and not all_farms and not farm_ids:
        own = farm_ids_of(actor)
        if len(own) != 1:
            raise ValidationError({"farm_ids": [CHOOSE_ONE_OF_YOURS]})
        farm_ids = list(own)
    return resolve_scope(producer_id, roles, farm_ids, all_farms)


def current_scope(user):
    """Lo que la cuenta ya tiene, para validar roles nuevos sin pedir el alcance otra vez."""
    return {farm.pk for farm in user.farms.all()}, user.all_farms


def change_scope(actor, user, roles, farm_ids, all_farms) -> tuple[bool, list] | None:
    """El alcance nuevo de `user` si cambia, o `None` si queda igual. No guarda: la relación se
    escribe con la cuenta ya guardada.

    Solo quien alcanza todas las fincas (el Productor, la cuenta técnica o un empleado con «todas»
    al que se le delegó) cambia el alcance de un empleado, y nunca da más del que tiene. Mientras
    el empleado tenga labores por hacer en alguna de las fincas que deja, no se cambia: primero se
    reasignan o se registran.
    """
    if user.groups.filter(role__code__in=(ADMINISTRATOR, PRODUCER)).exists():
        raise ValidationError({"farm_ids": ["Esta cuenta no lleva fincas."]})
    current, was_all = current_scope(user)
    new_all, farms = resolve_scope(user.producer_id, roles, farm_ids, all_farms, current=current)
    new_ids = {farm.pk for farm in farms}
    if new_all == was_all and new_ids == current:
        return None
    if not reaches_all_farms(actor):
        raise PermissionDenied(ONLY_ALL_FARMS_CHANGE)
    left = _farms_left(user, current, was_all, new_all, new_ids)
    work = [pending_work(user, farm_id) for farm_id in left]
    total = PendingWork(
        blocking=sum(item.blocking for item in work), kept=sum(item.kept for item in work)
    )
    if total.blocking:
        raise AccountHasPendingWork(total.blocking, total.kept)
    return new_all, farms


def _farms_left(user, current, was_all, new_all, new_ids) -> set:
    """Las fincas que la cuenta deja: las que tenía y ya no tiene. Con «todas» como punto de
    partida, todas las del productor que no queden en la lista nueva."""
    if new_all:
        return set()
    if was_all:
        everything = set(
            _farm_model().objects.filter(producer_id=user.producer_id).values_list("pk", flat=True)
        )
        return everything - new_ids
    return current - new_ids


def keeps_scope_for(roles, user) -> None:
    """Que el alcance que la cuenta ya tiene cumpla lo que piden los roles nuevos (al cambiar los
    roles sin enviar fincas)."""
    current, was_all = current_scope(user)
    resolve_scope(user.producer_id, roles, current, was_all, current=current)


def accounts_breaking(role, scope) -> int:
    """Cuántas cuentas con `role` no cumplirían `scope` como alcance del rol."""
    holders = User.objects.filter(groups=role.group).prefetch_related("farms")
    if scope == Role.FarmScope.ALL:
        return sum(1 for holder in holders if not holder.all_farms)
    if scope == Role.FarmScope.ONE:
        return sum(1 for holder in holders if holder.all_farms or len(holder.farms.all()) != 1)
    return 0
