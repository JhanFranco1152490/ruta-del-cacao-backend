"""Códigos consecutivos e inmutables de fincas y parcelas (`F02`, `P05`).

El número lo asigna el servidor con un contador que vive en la fila del dueño y solo sube: un
registro eliminado no devuelve el suyo, así que un código nunca se vuelve a usar para otra cosa.
"""

import re

from django.db import models
from django.db.models import F

MIN_DIGITS = 2


def format_code(letter: str, number: int) -> str:
    """La letra y el número con al menos dos cifras: `F02`, `P10` y `P100`."""
    return f"{letter}{number:0{MIN_DIGITS}d}"


def number_from_query(letter: str, term: str) -> int | None:
    """El número que una búsqueda pide como código (`F02`, `f2`, `2`), o `None` si el texto no
    parece un código y debe buscarse como nombre."""
    match = re.fullmatch(rf"(?:{letter}\s*)?(\d+)", (term or "").strip(), flags=re.IGNORECASE)
    if match is None:
        return None
    number = int(match.group(1))
    return number or None


def next_number(model: type[models.Model], pk, field: str) -> int:
    """Toma el siguiente número del contador `field` de la fila `pk` de `model`.

    Bloquea la fila hasta el final de la transacción, así que dos altas simultáneas del mismo dueño
    nunca reciben el mismo número. Debe llamarse dentro de una transacción y, si la alta puede ser
    un reenvío, después de comprobar que no lo es: un reenvío no gasta número.
    """
    locked = model.objects.select_for_update().filter(pk=pk)
    locked.update(**{field: F(field) + 1})
    return locked.values_list(field, flat=True).get()
