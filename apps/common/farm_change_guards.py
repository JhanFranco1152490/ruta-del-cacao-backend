"""Lo que impide cambiar a una cuenta de la finca en la que trabaja.

Las cuentas no conocen las apps que les asignan trabajo en una finca (actividades hoy; controles o
cosechas después), y ninguna app importa de otra. Cada una registra aquí, en su `ready()`, una
función que dice cuánto trabajo tiene la cuenta en esa finca: lo que obliga a esperar (hay que
reasignarlo o terminarlo antes) y lo que se queda a su nombre sin impedir el cambio.
"""

from collections.abc import Callable
from typing import Any, NamedTuple


class PendingWork(NamedTuple):
    blocking: int
    kept: int


Guard = Callable[[Any, Any], PendingWork]

_guards: dict[str, Guard] = {}


def register_guard(name: str, guard: Guard) -> None:
    # Por nombre: volver a cargar un módulo reemplaza el registro en vez de duplicarlo.
    _guards[name] = guard


def pending_work(account, farm_id) -> PendingWork:
    """El trabajo de `account` en la finca `farm_id`, sumado entre todas las apps."""
    results = [guard(account, farm_id) for guard in _guards.values()]
    return PendingWork(
        blocking=sum(result.blocking for result in results),
        kept=sum(result.kept for result in results),
    )
