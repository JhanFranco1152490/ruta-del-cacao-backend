import uuid
from collections.abc import Callable, Iterable, Mapping
from datetime import date, datetime
from decimal import Decimal

from django.db import models


class AuditEventBase(models.Model):
    """Lo común a los historiales de cambios de un registro del dominio.

    Cada historial concreto declara sus `Action` (con `action` como campo de esas opciones), el
    registro al que apunta y `actor`. Por defecto solo se guardan los nombres de los campos que
    cambiaron, nunca sus valores, para que el historial no repita datos personales. Un historial
    puede guardar además los valores solo si el registro no tiene ningún dato personal (un insumo).
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    changed_fields = models.JSONField(default=list, blank=True)
    occurred_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        abstract = True
        ordering = ["-occurred_at"]

    @classmethod
    def record(cls, *, action: str, changed_fields: Iterable[str] = (), **fields):
        if action not in cls.Action.values:
            raise ValueError("Unsupported audit action.")

        normalized_fields = sorted(set(changed_fields))
        if any(not isinstance(field, str) or not field for field in normalized_fields):
            raise ValueError("Changed fields must be non-empty strings.")

        return cls.objects.create(action=action, changed_fields=normalized_fields, **fields)


def _as_api_value(value, decimal_places: int | None):
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, Decimal) and decimal_places is not None:
        return f"{value:.{decimal_places}f}"
    if isinstance(value, uuid.UUID | Decimal):
        return str(value)
    return value


def field_changes(
    before: Mapping[str, object],
    after: Mapping[str, object],
    *,
    fields: Iterable[str] | None = None,
    decimal_places: int | None = None,
) -> dict:
    """El valor anterior y el nuevo de cada campo que cambió, con los valores como los entrega la
    API (fechas en ISO, UUID y decimales en texto), listos para guardarse en JSON.

    Es para los historiales que deben mostrar qué valor tenía cada campo. Solo sirve para
    registros sin datos personales: una persona se guarda por su id, nunca por su nombre.
    Un campo que falta en uno de los lados cuenta como vacío.

    Sin `fields`, compara los dos lados y deja solo lo que cambió. Con `fields`, deja esos campos
    tal cual: quien llama ya sabe qué cambió, o en un alta quiere todos aunque alguno siga vacío.
    `decimal_places` escribe los decimales con esas cifras, como los muestra la API del registro.
    """
    if fields is None:
        names = sorted(
            name for name in before.keys() | after.keys() if before.get(name) != after.get(name)
        )
    else:
        names = sorted(set(fields))
    return {
        name: {
            "before": _as_api_value(before.get(name), decimal_places),
            "after": _as_api_value(after.get(name), decimal_places),
        }
        for name in names
    }


STATUS_FIELD = "is_active"


def record_update_events(
    record: Callable[..., object], changed: Iterable[str], *, updated: str, status_changed: str
) -> None:
    """Deja en el historial lo que una edición cambió, en eventos separados: los campos de
    contenido como `updated` y la activación o desactivación como `status_changed`.

    `record` recibe `action` y `changed_fields`, y ya lleva el registro y quien actuó. Una edición
    que cambia las dos cosas deja dos eventos; una que no cambia nada, ninguno.
    """
    changed = list(changed)
    content = [name for name in changed if name != STATUS_FIELD]
    if content:
        record(action=updated, changed_fields=content)
    if STATUS_FIELD in changed:
        record(action=status_changed, changed_fields=[STATUS_FIELD])
