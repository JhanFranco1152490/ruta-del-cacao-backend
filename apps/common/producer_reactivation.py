"""Reactivar a un productor y a su cuenta Productor van juntos.

Son la misma persona: quien reactiva una de las dos quiere que esa persona vuelva a entrar, y con
los dos estados separados había que reactivarla dos veces, en dos pantallas. El estado del
expediente es de la app de productores y el de la cuenta, de la de cuentas, y ninguna app importa
de otra (ver AGENTS.md). El punto de encuentro es este módulo: cada una registra en su `ready()`
cómo reactiva lo suyo, y la otra lo llama dentro de su propia transacción.

Las dos direcciones bloquean en el mismo orden, primero el productor y después la cuenta, para no
interbloquearse si coinciden.
"""

from collections.abc import Callable
from typing import Any

# Reactiva el productor si está inactivo: `(producer_id)`.
_producer_reactivator: Callable[[Any], None] | None = None
# Reactiva la cuenta Productor del productor si está desactivada, a nombre de quien actúa:
# `(producer_id, actor)`.
_account_reactivator: Callable[[Any, Any], None] | None = None


def register_producer_reactivator(reactivator: Callable[[Any], None]) -> None:
    global _producer_reactivator
    _producer_reactivator = reactivator


def register_account_reactivator(reactivator: Callable[[Any, Any], None]) -> None:
    global _account_reactivator
    _account_reactivator = reactivator


def reactivate_producer(producer_id: Any) -> None:
    if _producer_reactivator is None:
        raise RuntimeError("La app de productores no registró cómo reactivar un productor.")
    _producer_reactivator(producer_id)


def reactivate_producer_account(producer_id: Any, actor: Any) -> None:
    if _account_reactivator is None:
        raise RuntimeError("La app de cuentas no registró cómo reactivar la cuenta Productor.")
    _account_reactivator(producer_id, actor)
