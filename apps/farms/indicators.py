"""Las fincas de los paneles de indicadores: cuáles alcanza quien consulta y cómo se nombran."""

from apps.common.codes import format_code
from apps.common.contracts.indicators import ScopedFarm
from apps.common.ownership import owner_filter

from .models import Farm
from .services.scope import readable_farms


def farm_scope(actor, *, everyone=False, producer_id=None, farm_id=None):
    """Los ids de las fincas del panel, como subconsulta.

    `everyone` pide las de todos los productores, que solo se dan a quien ya las lee todas (la
    asociación y la cuenta técnica); a cualquier otra cuenta le quedan las suyas. Sin `everyone`,
    las del productor de `actor`, y un empleado solo las que trabaja. `producer_id` solo acota a la
    cuenta técnica, como en las listas. Las fincas inactivas cuentan: lo que produjeron sigue
    siendo suyo.
    """
    if everyone:
        farms = readable_farms(actor)
    else:
        farms = Farm.objects.filter(**owner_filter(actor, farm="id"))
        if producer_id is not None and actor.is_superuser:
            farms = farms.filter(producer_id=producer_id)
    if farm_id is not None:
        farms = farms.filter(pk=farm_id)
    return farms.values("pk")


def scoped_farms(farm_ids) -> list[ScopedFarm]:
    farms = Farm.objects.filter(pk__in=farm_ids).select_related("producer")
    return [
        ScopedFarm(
            farm_id=farm.pk,
            code=format_code("F", farm.number),
            name=farm.name,
            municipality_code=farm.municipality_code,
            producer_id=farm.producer_id,
            producer_member_code=farm.producer.member_code,
            producer_first_name=farm.producer.first_name,
            producer_last_name=farm.producer.last_name,
        )
        for farm in farms
    ]
