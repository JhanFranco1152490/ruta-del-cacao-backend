from datetime import datetime

from apps.common.contracts.lot_history import STAGE_KINDS, LotHistoryStage

_PROCESS_ORDER = {kind: position for position, kind in enumerate(STAGE_KINDS)}


def _key(stage: LotHistoryStage):
    # El día manda; en el mismo día, el orden del proceso, porque la cosecha no tiene hora y no
    # puede quedar después del lote que se conformó con ella. Entre etapas del mismo tipo, la que
    # solo tiene fecha va antes de la que tiene hora, y si no hay hora, cuándo se registró.
    has_time = stage.occurred_at is not None
    return (
        stage.occurred_on,
        _PROCESS_ORDER[stage.kind],
        has_time,
        stage.occurred_at if has_time else datetime.min,
        stage.recorded_at,
    )


def order_stages(stages: list[LotHistoryStage]) -> list[LotHistoryStage]:
    """Las etapas de la más antigua a la más reciente."""
    return sorted(stages, key=_key)
