"""Las alertas: qué condiciones merecen un aviso y quién lo recibe.

Cada app sabe cuándo algo suyo merece un aviso (una actividad que se acerca o se venció), pero
ninguna app importa de otra. Por eso se encuentran aquí:

- una app con condiciones periódicas registra en su `ready()` un evaluador, una función que con
  la fecha de hoy devuelve los avisos que corresponden. Solo calcula: no escribe;
- la app de notificaciones registra la función que los guarda (`register_sink`);
- una app que detecta una condición al guardar algo llama a `notify()` dentro de su transacción.
"""

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import date

from django.db import transaction


@dataclass(frozen=True)
class NotificationDraft:
    """Un aviso por crear. `condition_key` lo hace único para esa persona dentro de su tipo, así
    que evaluar otra vez no lo repite; `thread_key` agrupa los avisos de lo mismo, y el más nuevo
    de una persona oculta los anteriores."""

    recipient_id: int
    kind: str
    condition_key: str
    thread_key: str
    severity: str = "normal"
    activity_id: object = None
    condition_date: date | None = None


Evaluator = Callable[[date], Iterable[NotificationDraft]]
Sink = Callable[[list[NotificationDraft]], int]

_evaluators: dict[str, Evaluator] = {}
_sink: Sink | None = None


def register_evaluator(name: str, evaluator: Evaluator) -> None:
    # Por nombre: volver a cargar un módulo reemplaza el registro en vez de duplicarlo.
    _evaluators[name] = evaluator


def evaluators() -> dict[str, Evaluator]:
    return dict(_evaluators)


def register_sink(sink: Sink) -> None:
    global _sink
    _sink = sink


def notify(drafts: Iterable[NotificationDraft]) -> None:
    """Crea los avisos cuando se confirme la transacción en curso: si lo que los causó se
    revierte, no hay aviso."""
    pending = list(drafts)
    transaction.on_commit(lambda: _write(pending))


def _write(drafts: list[NotificationDraft]) -> int:
    if _sink is None:
        # Sin quien los guarde, los avisos se perderían en silencio.
        raise RuntimeError("No hay dónde guardar las notificaciones.")
    return _sink(drafts)
