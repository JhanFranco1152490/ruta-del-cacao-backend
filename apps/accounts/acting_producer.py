import uuid

from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError

from .access import get_producer_model

ACTING_PRODUCER_HEADER = "X-Acting-Producer"


def resolve_acting_producer(user, request) -> uuid.UUID | None:
    """El productor bajo el que opera `user` en esta petición, o `None` si no eligió ninguno.

    Solo lo acepta de un superusuario: un encabezado de otra cuenta es un error y no se ignora,
    para que nadie crea que está operando bajo un productor que no se aplicó. Se usan las
    excepciones de DRF y no las propias de la API porque este módulo lo carga la autenticación,
    que DRF importa al configurarse, y las propias dependen de esa misma configuración.
    """
    raw = request.headers.get(ACTING_PRODUCER_HEADER)
    if raw is None:
        return None
    if not user.is_superuser:
        raise PermissionDenied("Solo la cuenta técnica puede actuar bajo un productor.")
    try:
        producer_id = uuid.UUID(raw)
    except ValueError:
        raise ValidationError("El productor activo no es válido.") from None
    if not get_producer_model().objects.filter(pk=producer_id).exists():
        raise NotFound("El productor activo no existe.")
    return producer_id
