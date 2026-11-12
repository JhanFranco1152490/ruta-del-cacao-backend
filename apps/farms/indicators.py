"""Las fincas de los paneles de indicadores: cuáles alcanza quien consulta y cómo se nombran."""

from apps.common.codes import format_code
from apps.common.contracts.indicators import ScopedFarm
from apps.common.ownership import owner_filter

from .models import Farm
from .services.scope import readable_farms


def farm_scope(actor, *, everyone=False, producer_id=None, farm_id=None, municipality_code=None):
    """Los ids de las fincas de un panel o un reporte, como subconsulta.

    `everyone` pide las de todos los productores, que solo se dan a quien ya las lee todas (la
    asociación y la cuenta técnica); a cualquier otra cuenta le quedan las suyas. Sin `everyone`,
    las del productor de `actor`, y un empleado solo las que trabaja. Las fincas inactivas cuentan:
    lo que produjeron sigue siendo suyo.

    `producer_id` acota entre todas (los reportes de la asociación) o, sin `everyone`, solo a la
    cuenta técnica, como en las listas: un productor que lo mande sigue viendo lo suyo. Entre
    todas no amplía a nadie, porque se aplica sobre lo que `actor` ya lee.
    """
    if everyone:
        farms = readable_farms(actor)
        if producer_id is not None:
            farms = farms.filter(producer_id=producer_id)
    else:
        farms = Farm.objects.filter(**owner_filter(actor, farm="id"))
        if producer_id is not None and actor.is_superuser:
            farms = farms.filter(producer_id=producer_id)
    if farm_id is not None:
        farms = farms.filter(pk=farm_id)
    if municipality_code is not None:
        farms = farms.filter(municipality_code=municipality_code)
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
