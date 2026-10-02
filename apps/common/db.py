from django.db import IntegrityError


def constraint_name(error: IntegrityError) -> str | None:
    """La restricción de la base que rechazó la escritura, para traducir el choque a un error
    de negocio (un nombre repetido) en vez de un 500."""
    diagnostics = getattr(error.__cause__, "diag", None)
    return getattr(diagnostics, "constraint_name", None)
