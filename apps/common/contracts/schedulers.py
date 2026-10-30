"""Quién alcanza una finca con un permiso: a esas cuentas les llegan los avisos de algo que hay que
resolver en esa finca. Las que pueden programar labores reciben los de una actividad atrasada o un
control que alguien pidió; las que registran volteos o la bitácora del secado, los de un lote.

Se decide por el permiso y no por el rol, que en un rol propio puede llamarse de cualquier
forma. Lo usan los evaluadores de varias apps, por eso vive aquí.
"""

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.db.models import Q

from ..ownership import reaches_all_farms

SCHEDULE_PERMISSION = "activities.add_agriculturalactivity"


class FarmAccounts:
    """Las cuentas activas de unos productores con un permiso (`"app_label.codename"`), con las
    fincas que alcanzan. Se carga una vez para todo lo que se evalúa: las consultas crecen con las
    cuentas, no con los registros."""

    def __init__(self, producer_ids, permission: str):
        self._by_producer: dict = {}
        if not producer_ids:
            return
        app_label, codename = permission.split(".", 1)
        granted = Permission.objects.filter(content_type__app_label=app_label, codename=codename)
        accounts = (
            get_user_model()
            .objects.filter(
                Q(user_permissions__in=granted) | Q(groups__permissions__in=granted),
                producer_id__in=producer_ids,
                is_active=True,
                is_superuser=False,
            )
            .distinct()
            .prefetch_related("farms")
        )
        for account in accounts:
            # `None`: todas las fincas, también las que se registren después.
            farm_ids = None if reaches_all_farms(account) else {f.pk for f in account.farms.all()}
            self._by_producer.setdefault(account.producer_id, []).append((account.pk, farm_ids))

    def on_farm(self, producer_id, farm_id) -> set:
        """Los ids de las cuentas que alcanzan esa finca con el permiso."""
        return {
            account_id
            for account_id, farm_ids in self._by_producer.get(producer_id, [])
            if farm_ids is None or farm_id in farm_ids
        }

    def on_farm_with(self, producer_id, farm_id, responsible) -> set:
        """Las de la finca y quien responde por la etapa, si su cuenta está activa: es quien tiene
        que hacer lo que falta, tenga o no el permiso."""
        accounts = self.on_farm(producer_id, farm_id)
        if responsible is not None and responsible.is_active:
            accounts.add(responsible.pk)
        return accounts


class Schedulers(FarmAccounts):
    """Las cuentas que pueden programar labores en cada finca."""

    def __init__(self, producer_ids):
        super().__init__(producer_ids, SCHEDULE_PERMISSION)
