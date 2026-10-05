"""Pasos comunes de editar un registro con bloqueo optimista por `version`."""

from collections.abc import Callable, Iterable

from django.db import models

from .db import save_translating_unique


def check_expected_version(
    row: models.Model,
    expected_version: int,
    *,
    stale: Callable[[], Exception],
    already_applied: Callable[[], bool] | None = None,
) -> bool:
    """Compara la versión que leyó el cliente con la del registro bloqueado.

    Devuelve `False` si coincide y quien llama sigue con la edición. Si no coincide lanza
    `stale()`, salvo que `already_applied` diga que el registro ya tiene lo que se pide: una cola
    sin conexión reintenta cuando no recibió la respuesta aunque el servidor sí haya aplicado el
    cambio, y mandar eso a revisión manual solo molestaría. En ese caso devuelve `True` y quien
    llama responde con el registro tal cual, sin escribir nada.
    """
    if row.version == expected_version:
        return False
    if already_applied is not None and already_applied():
        return True
    raise stale()


def save_next_version(
    row: models.Model,
    update_fields: Iterable[str],
    *,
    constraint: str,
    duplicate: Callable[[], Exception],
) -> None:
    """Sube la versión y guarda solo `update_fields` (más `version` y `updated_at`), traduciendo
    el choque con la restricción única `constraint` a `duplicate()`."""
    row.version += 1
    fields = [*update_fields, "version", "updated_at"]
    save_translating_unique(
        lambda: row.save(update_fields=fields),
        constraint=constraint,
        duplicate=duplicate,
    )
