"""Bloqueo de la raíz de un conjunto de filas, para que dos operaciones nunca se esperen entre sí.

La finca es la raíz de todo lo que cuelga de ella (parcelas, fichas, cosechas). Toda escritura
bajo una finca toma **solo** el bloqueo de la finca, y nunca el de las filas de abajo: con un único
bloqueo no puede haber dos operaciones esperándose una a la otra, y una entidad nueva no tiene que
acordarse de ningún orden. El costo es que dos escrituras bajo la misma finca se atienden una tras
otra; duran milisegundos. Lo lento (subir un archivo, un reporte) va fuera de la transacción.
"""

from django.db import models

from .exceptions import ApiError


def lock_root_row(root_model: type[models.Model], root_id):
    """La fila raíz, bloqueada hasta el final de la transacción, o `None` si ya no existe."""
    return root_model.objects.select_for_update().filter(pk=root_id).first()


def lock_aggregate_root(
    model: type[models.Model],
    pk,
    *,
    root: str,
    scope: dict,
    not_found: type[ApiError],
):
    """Bloquea la raíz de la fila `pk` de `model` y devuelve `(fila, raíz)`.

    `root` es la ruta de relaciones desde la fila hasta su raíz (`"farm"` para una parcela,
    `"plot__farm"` para algo que cuelga de ella) y `scope` lo que limita qué filas puede ver quien
    llama (las de su productor). Responde `not_found` si la fila no existe o está fuera del
    alcance: distinguirlas confirmaría que existe. Debe llamarse dentro de una transacción.
    """
    root_model = model
    for relation in root.split("__"):
        root_model = root_model._meta.get_field(relation).related_model
    root_id = model.objects.filter(pk=pk, **scope).values_list(f"{root}_id", flat=True).first()
    if root_id is None:
        raise not_found()
    locked_root = lock_root_row(root_model, root_id)
    # Otra operación pudo eliminar la fila mientras se esperaba el bloqueo: se vuelve a leer ya con
    # la raíz bloqueada, así que lo que se lee es lo que nadie más puede cambiar.
    row = model.objects.filter(pk=pk).first() if locked_root is not None else None
    if row is None:
        raise not_found()
    return row, locked_root
