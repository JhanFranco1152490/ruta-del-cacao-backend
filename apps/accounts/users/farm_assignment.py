"""Las fincas en las que trabaja un empleado: quién las asigna, cuándo son obligatorias y cuáles
valen. Un empleado puede trabajar en varias fincas del mismo productor (por ejemplo, vecinas)."""

from django.db.models import Q
from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.common.farm_change_guards import PendingWork, pending_work
from apps.common.roles import is_employee

from ..access import roles_of
from ..exceptions import AccountHasPendingWork
from ..models import User
from ..registry import FIELD_PERMISSIONS
from ..system_roles import ADMINISTRATOR, PRODUCER

FARM_REQUIRED = "Indica al menos una finca en la que trabaje."
FARM_NOT_AVAILABLE = "Elige fincas activas del productor."
OWN_FARMS_ONLY = "Solo puedes crear cuentas para las fincas en las que trabajas."
CHOOSE_ONE_OF_YOURS = "Indica en cuál de tus fincas va a trabajar."
ONLY_THE_PRODUCER = "Solo el productor cambia las fincas de un empleado."


def roles_need_farm(roles) -> bool:
    """Si alguno de los roles trae un permiso de campo: sin finca, ese permiso no alcanza nada."""
    return any(role.permission_codes & FIELD_PERMISSIONS for role in roles)


def needs_farm(user) -> bool:
    """Si a la cuenta le falta finca: es de un empleado con permisos de campo y no tiene ninguna.
    Lee las fincas con `.all()` para aprovechar las que ya vienen precargadas en una lista."""
    return not user.farms.all() and is_employee(user) and roles_need_farm(roles_of(user))


def employees_with_field_permissions():
    """Los ids de los empleados con algún permiso de campo, para filtrar un listado."""
    field_permission = Q()
    for code in FIELD_PERMISSIONS:
        app_label, codename = code.split(".")
        # En una sola condición: las dos partes deben cumplirse en el mismo permiso.
        field_permission |= Q(
            groups__permissions__content_type__app_label=app_label,
            groups__permissions__codename=codename,
        )
    return (
        User.objects.filter(field_permission, producer__isnull=False, is_superuser=False)
        .exclude(groups__role__code=PRODUCER)
        .values("pk")
    )


def farm_ids_of(user) -> set:
    return {farm.pk for farm in user.farms.all()} if user.pk else set()


def farms_for(producer_id, roles, farm_ids, *, current=frozenset()) -> list:
    """Las fincas que le corresponden a una cuenta de empleado con esos roles.

    Si los roles traen permisos de campo, al menos una. Cada una debe ser una finca activa del
    mismo productor; las que la cuenta ya tiene (`current`) se conservan aunque se hayan
    desactivado. Una finca ajena o inexistente responde igual que una inactiva: distinguirlas
    confirmaría que existe.
    """
    wanted = set(farm_ids or ())
    if not wanted:
        if roles_need_farm(roles):
            raise ValidationError({"farm_ids": [FARM_REQUIRED]})
        return []
    farm_model = User._meta.get_field("farms").related_model
    farms = list(farm_model.objects.filter(pk__in=wanted, producer_id=producer_id))
    if len(farms) != len(wanted) or any(
        not (farm.is_active or farm.pk in current) for farm in farms
    ):
        raise ValidationError({"farm_ids": [FARM_NOT_AVAILABLE]})
    return farms


def farms_for_new_account(actor, producer_id, roles, farm_ids) -> list:
    """Las fincas de un empleado que se está creando.

    El Productor (y la cuenta técnica) elige entre todas sus fincas. Un empleado de confianza con
    permiso de crear cuentas solo suma gente a las fincas en las que él trabaja: pedir otra es un
    `403`; si no indica ninguna y trabaja en una sola, la cuenta nueva la toma.
    """
    if is_employee(actor):
        own = farm_ids_of(actor)
        if not set(farm_ids or ()) <= own:
            raise PermissionDenied(OWN_FARMS_ONLY)
        if not farm_ids and roles_need_farm(roles):
            if len(own) != 1:
                raise ValidationError({"farm_ids": [CHOOSE_ONE_OF_YOURS]})
            farm_ids = list(own)
    return farms_for(producer_id, roles, farm_ids)


def change_farms(actor, user, roles, farm_ids) -> list | None:
    """Las fincas nuevas de `user` si cambian, o `None` si quedan igual. No guarda: la relación
    se escribe con la cuenta ya guardada.

    Solo el Productor (o la cuenta técnica) cambia las fincas de un empleado. Mientras tenga
    labores por hacer en alguna de las fincas que deja, no se cambia: primero se reasignan o se
    registran.
    """
    if user.groups.filter(role__code__in=(ADMINISTRATOR, PRODUCER)).exists():
        raise ValidationError({"farm_ids": ["Esta cuenta no lleva fincas."]})
    current = farm_ids_of(user)
    farms = farms_for(user.producer_id, roles, farm_ids, current=current)
    if {farm.pk for farm in farms} == current:
        return None
    if is_employee(actor):
        raise PermissionDenied(ONLY_THE_PRODUCER)
    left = current - {farm.pk for farm in farms}
    work = [pending_work(user, farm_id) for farm_id in left]
    total = PendingWork(
        blocking=sum(item.blocking for item in work), kept=sum(item.kept for item in work)
    )
    if total.blocking:
        raise AccountHasPendingWork(total.blocking, total.kept)
    return farms
