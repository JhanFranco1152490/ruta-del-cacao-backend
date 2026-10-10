import uuid
from collections.abc import Callable, Iterable

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
