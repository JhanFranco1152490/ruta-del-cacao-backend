from rest_framework.exceptions import ValidationError

from .exceptions import ProducerRequired
from .roles import is_employee


def reaches_all_farms(actor) -> bool:
    """Si `actor` alcanza todas las fincas de su productor: la cuenta Productor y la técnica. Un
    empleado solo alcanza las fincas en las que trabaja."""
    return not is_employee(actor)


def own_farms(actor):
    """Los ids de las fincas en las que trabaja `actor`, como subconsulta: quien la usa en un
    filtro no paga una consulta aparte."""
    return actor.farms.values("pk")


def reaches_farm(actor, farm_id) -> bool:
    """Si `actor` alcanza la finca `farm_id`, que ya se sabe de su productor."""
    return reaches_all_farms(actor) or actor.farms.filter(pk=farm_id).exists()


def owner_filter(actor, field: str = "producer_id", *, farm: str | None = None) -> dict:
    """La restricción de productor para buscar algo que ya existe, lista para `**`.

    El productor y su gente alcanzan lo suyo. La cuenta técnica (superusuario) alcanza lo de
    cualquiera: el recurso ya dice de quién es, así que no necesita elegir un productor aparte.

    `farm` es la ruta desde el recurso hasta el id de su finca (`"farm_id"` en una parcela,
    `"plot__farm_id"` en lo que cuelga de ella, `"id"` en la finca misma). Todo lo que cuelga de
    una finca la indica: así un empleado queda limitado a las suyas, y uno sin finca asignada no
    alcanza nada (la lista de sus fincas está vacía y no encuentra filas).
    """
    if actor.is_superuser:
        return {}
    scope = {field: actor.producer_id}
    if farm is not None and not reaches_all_farms(actor):
        scope[f"{farm}__in"] = own_farms(actor)
    return scope


def owns(actor, producer_id) -> bool:
    """Si `actor` puede tratar como suyo algo del productor `producer_id`."""
    return actor.is_superuser or (producer_id is not None and actor.producer_id == producer_id)


def resolve_target_producer(actor, data: dict, producer_model, *, inactive):
    """El id del productor de un registro nuevo: el de la sesión, o el que nombra la cuenta
    técnica.

    La cuenta técnica no tiene un productor propio, así que lo manda en `producer_id`; debe
    existir y estar activo, y si no lo está se lanza `inactive()`. Para cualquier otra cuenta
    mandarlo es un error, aunque sea el suyo: un registro nunca se crea a nombre de otro
    productor. Quita `producer_id` de `data`.
    """
    requested = data.pop("producer_id", None)
    if not actor.is_superuser:
        if requested is not None:
            raise ValidationError({"producer_id": ["Campo no permitido."]})
        if actor.producer_id is None:
            raise ProducerRequired()
        return actor.producer_id
    if requested is None:
        raise ValidationError({"producer_id": ["Este campo es requerido."]})
    producer = producer_model.objects.filter(pk=requested).first()
    if producer is None:
        raise ValidationError({"producer_id": ["El productor no existe."]})
    if producer.status != producer_model.Status.ACTIVE:
        raise inactive()
    return producer.pk
