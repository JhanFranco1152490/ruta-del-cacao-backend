"""Las alertas: qué condiciones merecen un aviso y quién lo recibe.

Cada app sabe cuándo algo suyo merece un aviso (una actividad que se acerca o se venció), pero
ninguna app importa de otra. Por eso se encuentran aquí:

- una app con condiciones periódicas registra en su `ready()` un evaluador, una función que con
  la fecha de hoy y la hora de la evaluación devuelve los avisos que corresponden. Solo calcula:
  no escribe;
- la app de notificaciones registra cómo se guardan (`register_sink`);
- una app que detecta una condición al guardar algo llama a `notify()` dentro de su transacción;
  cuando llega lo que un aviso pedía, `resolve()`; y cuando corrige un registro que ya no cumple
  la condición de su aviso, `withdraw()`.
"""

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

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
    detection_id: object = None
    condition_date: date | None = None
    lot_id: object = None
    fermentation_turn_id: object = None
    drying_log_id: object = None
    condition_at: datetime | None = None


@dataclass(frozen=True)
class Deviation:
    """Una medición fuera de los parámetros, como la ve quien acaba de registrarla: qué desvío es,
    el valor que se comparó y el límite que cruzó (`"7.6-8.5"` en un rango)."""

    kind: str
    severity: str
    value: str
    limit: str


def deviation_drafts(
    deviations: Iterable[Deviation],
    recipient_ids: Iterable,
    *,
    lot_id,
    condition_at: datetime | None,
    fermentation_turn_id=None,
    drying_log_id=None,
) -> list[NotificationDraft]:
    """Un aviso por desvío y por persona, del volteo o de la bitácora que lo midió."""
    record = fermentation_turn_id if fermentation_turn_id is not None else drying_log_id
    if (fermentation_turn_id is None) == (drying_log_id is None):
        raise ValueError("Un desvío es de un solo registro.")
    return [
        NotificationDraft(
            recipient_id=recipient_id,
            kind=deviation.kind,
            severity=deviation.severity,
            # Guardar dos veces el mismo registro (un reenvío de la cola) no repite el aviso.
            condition_key=f"{record}:{deviation.kind}",
            # Cada desvío en su hilo: el de hoy reemplaza al de ayer del mismo lote, pero un
            # secado lento no oculta un sobresecado.
            thread_key=f"lot:{lot_id}:{deviation.kind}",
            lot_id=lot_id,
            fermentation_turn_id=fermentation_turn_id,
            drying_log_id=drying_log_id,
            condition_at=condition_at,
        )
        for deviation in deviations
        for recipient_id in sorted(recipient_ids, key=str)
    ]


# El día cuenta para lo que se mide en fechas (una actividad) y la hora para lo que se mide en
# horas (un volteo); cada evaluador usa lo que necesita.
Evaluator = Callable[[date, datetime], Iterable[NotificationDraft]]


@dataclass(frozen=True)
class NotificationSink:
    """Lo que la app de notificaciones hace con los avisos que le piden las demás."""

    # Guarda los borradores que todavía no existen y dice cuántos son nuevos.
    create: Callable[[list[NotificationDraft]], int]
    # Marca como resueltos los avisos de un lote de esos tipos que todavía no lo están.
    resolve: Callable[[Any, list[str]], int]
    # Borra los avisos de esos tipos de un volteo o de una bitácora.
    withdraw: Callable[..., int]


_evaluators: dict[str, Evaluator] = {}
_sink: NotificationSink | None = None


def register_evaluator(name: str, evaluator: Evaluator) -> None:
    # Por nombre: volver a cargar un módulo reemplaza el registro en vez de duplicarlo.
    _evaluators[name] = evaluator


def evaluators() -> dict[str, Evaluator]:
    return dict(_evaluators)


def register_sink(sink: NotificationSink) -> None:
    global _sink
    _sink = sink


# Las tres corren cuando se confirma la transacción en curso: si lo que las causó se revierte, no
# pasa nada.


def notify(drafts: Iterable[NotificationDraft]) -> None:
    """Crea los avisos."""
    pending = list(drafts)
    transaction.on_commit(lambda: _registered().create(pending))


def resolve(lot_id, kinds: Iterable[str]) -> None:
    """Deja como resueltos los avisos pendientes de un lote de esos tipos: llegó el registro que
    faltaba o el lote terminó la etapa."""
    pending = list(kinds)
    transaction.on_commit(lambda: _registered().resolve(lot_id, pending))


def withdraw(kinds: Iterable[str], *, fermentation_turn_id=None, drying_log_id=None) -> None:
    """Borra los avisos de esos tipos de un volteo o de una bitácora que se corrigió y ya no cumple
    su condición."""
    record = {
        name: value
        for name, value in (
            ("fermentation_turn_id", fermentation_turn_id),
            ("drying_log_id", drying_log_id),
        )
        if value is not None
    }
    if len(record) != 1:
        # Sin registro borraría los avisos de todos; con dos, no se sabe de cuál.
        raise ValueError("Se retiran los avisos de un solo registro.")
    pending = list(kinds)
    transaction.on_commit(lambda: _registered().withdraw(pending, **record))


def _registered() -> NotificationSink:
    if _sink is None:
        # Sin quien los guarde, los avisos se perderían en silencio.
        raise RuntimeError("No hay dónde guardar las notificaciones.")
    return _sink
