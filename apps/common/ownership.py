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
