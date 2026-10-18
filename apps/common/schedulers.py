"""Quién puede programar labores en una finca: a esas cuentas les llegan los avisos de algo que
hay que resolver programando (una actividad atrasada, un control que alguien pidió).

Se decide por el permiso y no por el rol, que en un rol propio puede llamarse de cualquier
forma. Lo usan los evaluadores de varias apps, por eso vive aquí.
"""

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.db.models import Q

from .ownership import reaches_all_farms

SCHEDULE_APP_LABEL = "activities"
SCHEDULE_CODENAME = "add_agriculturalactivity"


class Schedulers:
    """Las cuentas activas de unos productores que pueden programar, con las fincas que
    alcanzan. Se carga una vez para todo lo que se evalúa: las consultas crecen con las cuentas,
    no con los registros."""

    def __init__(self, producer_ids):
        self._by_producer: dict = {}
        if not producer_ids:
            return
        permission = Permission.objects.filter(
            content_type__app_label=SCHEDULE_APP_LABEL, codename=SCHEDULE_CODENAME
        )
        accounts = (
            get_user_model()
            .objects.filter(
                Q(user_permissions__in=permission) | Q(groups__permissions__in=permission),
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
        """Los ids de las cuentas que pueden programar en esa finca."""
        return {
            account_id
            for account_id, farm_ids in self._by_producer.get(producer_id, [])
            if farm_ids is None or farm_id in farm_ids
        }
