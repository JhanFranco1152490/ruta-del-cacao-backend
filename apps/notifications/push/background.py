"""Enviar una push sin que quien guardó el registro espere al servicio de push.

Cada dispositivo puede tardar hasta `PUSH_TIMEOUT_SECONDS`, y la petición que guarda una bitácora
no tiene por qué esperar a que un teléfono ajeno responda. La tarea corre en un grupo de hilos
pequeño: acota cuántos envíos simultáneos abre un pico de avisos y, al apagar el proceso, deja
terminar los que están en curso.
"""

from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor

from django.db import connections

from apps.common.exceptions import log_unhandled_error

_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="push")


def run_in_background(task: Callable[..., object], *args, where: str, **kwargs) -> Future:
    """Corre `task` fuera de la petición. Un fallo se registra (`where` dice dónde) y no se
    propaga: no hay a quién."""
    return _executor.submit(_run, task, args, kwargs, where)


def _run(task, args, kwargs, where) -> None:
    try:
        task(*args, **kwargs)
    except Exception as exc:
        log_unhandled_error(exc, where=where)
    finally:
        # La conexión a la base es del hilo: si no se cierra, se queda abierta hasta que el hilo
        # muera.
        connections.close_all()
