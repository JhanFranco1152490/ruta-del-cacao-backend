from collections.abc import Callable

from django.db import IntegrityError, models, transaction


def constraint_name(error: IntegrityError) -> str | None:
    """La restricción de la base que rechazó la escritura, para traducir el choque a un error
    de negocio (un nombre repetido) en vez de un 500."""
    diagnostics = getattr(error.__cause__, "diag", None)
    return getattr(diagnostics, "constraint_name", None)


def save_translating_unique(
    save: Callable[[], None],
    *,
    constraint: str,
    duplicate: Callable[[], Exception],
    find_existing: Callable[[], models.Model | None] | None = None,
) -> models.Model | None:
    """Corre `save` en un punto de guardado propio y traduce el choque con la restricción única
    `constraint` al error de negocio `duplicate()` (un nombre repetido) en vez de un 500. Cualquier
    otro choque se vuelve a lanzar. El punto de guardado deja usable la transacción de quien llama.

    `find_existing` es para las altas que se reintentan sin conexión: si dos envíos del mismo
    registro llegan a la vez, el segundo choca con el primero. Se llama antes que nada, porque
    según el orden en que PostgreSQL revise los índices el choque se reporta en la clave primaria
    o en el nombre, y un reenvío no es un nombre repetido. Si devuelve el registro, ese es el
    resultado; si devuelve `None`, el choque se trata como cualquier otro.
    """
    try:
        with transaction.atomic():
            save()
    except IntegrityError as error:
        if find_existing is not None and (existing := find_existing()) is not None:
            return existing
        if constraint_name(error) == constraint:
            raise duplicate() from None
        raise
    return None


def dependent_relations(model: type[models.Model], *, ignore=()) -> list:
    """Las relaciones inversas de otras tablas que apuntan a `model`, salvo las de los modelos de
    `ignore` (normalmente su historial de auditoría).

    Se recorren las relaciones del modelo en vez de una lista fija: así una tabla nueva que
    dependa del registro (cultivos, capturas, lotes) cuenta sin que nadie tenga que acordarse de
    agregarla. `include_hidden` incluye también las relaciones declaradas sin nombre inverso.
    """
    return [
        relation
        for relation in model._meta.get_fields(include_hidden=True)
        if relation.auto_created and not relation.concrete and relation.related_model not in ignore
    ]


def has_dependent_rows(instance: models.Model, *, ignore=()) -> bool:
    """Si alguna fila de otra tabla apunta a `instance`, salvo las de los modelos de `ignore`."""
    return any(
        relation.related_model._base_manager.filter(**{relation.field.name: instance}).exists()
        for relation in dependent_relations(type(instance), ignore=ignore)
    )
