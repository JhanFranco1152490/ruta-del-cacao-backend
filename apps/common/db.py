from django.db import IntegrityError, models


def constraint_name(error: IntegrityError) -> str | None:
    """La restricción de la base que rechazó la escritura, para traducir el choque a un error
    de negocio (un nombre repetido) en vez de un 500."""
    diagnostics = getattr(error.__cause__, "diag", None)
    return getattr(diagnostics, "constraint_name", None)


def has_dependent_rows(instance: models.Model, *, ignore=()) -> bool:
    """Si alguna fila de otra tabla apunta a `instance`, salvo las de los modelos de `ignore`
    (normalmente su historial de auditoría).

    Se recorren las relaciones del modelo en vez de una lista fija: así una tabla nueva que
    dependa del registro (cultivos, capturas, lotes) impide eliminarlo sin que nadie tenga que
    acordarse de agregarla. `include_hidden` incluye también las relaciones declaradas sin
    nombre inverso.
    """
    for relation in type(instance)._meta.get_fields(include_hidden=True):
        if not relation.auto_created or relation.concrete:
            continue
        if relation.related_model in ignore:
            continue
        lookup = {relation.field.name: instance}
        if relation.related_model._base_manager.filter(**lookup).exists():
            return True
    return False
