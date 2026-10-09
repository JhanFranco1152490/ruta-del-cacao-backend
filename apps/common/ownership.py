from rest_framework.exceptions import ValidationError

from .exceptions import ProducerRequired


def owner_filter(actor, field: str = "producer_id") -> dict:
    """La restricción de productor para buscar algo que ya existe, lista para `**`.

    El productor y su gente alcanzan lo suyo. La cuenta técnica (superusuario) alcanza lo de
    cualquiera: el recurso ya dice de quién es, así que no necesita elegir un productor aparte.
    """
    if actor.is_superuser:
        return {}
    return {field: actor.producer_id}


def owns(actor, producer_id) -> bool:
    """Si `actor` puede tratar como suyo algo del productor `producer_id`."""
    return actor.is_superuser or (producer_id is not None and actor.producer_id == producer_id)


def resolve_target_producer(actor, data: dict, producer_model):
    """El productor de un registro nuevo: el de la sesión, o el que nombra la cuenta técnica.

    La cuenta técnica no tiene un productor propio, así que lo manda en `producer_id` (y debe
    existir). Para cualquier otra cuenta mandarlo es un error, aunque sea el suyo: un registro
    nunca se crea a nombre de otro productor. Quita `producer_id` de `data`. Devuelve el productor;
    qué hacer si está inactivo lo decide quien llama.
    """
    requested = data.pop("producer_id", None)
    if not actor.is_superuser:
        if requested is not None:
            raise ValidationError({"producer_id": ["Campo no permitido."]})
        if actor.producer_id is None:
            raise ProducerRequired()
        return producer_model.objects.get(pk=actor.producer_id)
    if requested is None:
        raise ValidationError({"producer_id": ["Este campo es requerido."]})
    producer = producer_model.objects.filter(pk=requested).first()
    if producer is None:
        raise ValidationError({"producer_id": ["El productor no existe."]})
    return producer
