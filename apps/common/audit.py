import uuid
from collections.abc import Iterable

from django.db import models


class AuditEventBase(models.Model):
    """Lo común a los historiales de cambios de un registro del dominio.

    Cada historial concreto declara sus `Action` (con `action` como campo de esas opciones), el
    registro al que apunta y `actor`. Solo se guardan los nombres de los campos que cambiaron,
    nunca sus valores, para que el historial no repita datos personales.
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
