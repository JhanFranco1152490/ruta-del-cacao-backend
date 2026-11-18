"""Las etapas de la historia que son del propio lote: la cosecha de la que salió y su conformado.
Leen lo que `visible_lots` ya precarga, así que no hacen consultas."""

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from apps.common.contracts.lot_history import LotHistoryStage
from apps.common.serializers import full_name


@dataclass(frozen=True)
class HarvestData:
    harvest_id: Any
    variety: str
    # La versión de la ficha de la parcela al cosechar: dice cómo estaba sembrada.
    characterization_version: int
    collector: str
    green_weight_kg: Decimal


@dataclass(frozen=True)
class LotCreatedData:
    # Sin nombre si la cuenta que lo conformó se eliminó.
    created_by: str | None


def harvest_stage(lot) -> LotHistoryStage:
    harvest = lot.harvest
    return LotHistoryStage.on(
        "harvest",
        harvest.harvest_date,
        recorded_at=harvest.created_at,
        data=HarvestData(
            harvest_id=harvest.pk,
            variety=harvest.variety.name,
            characterization_version=harvest.characterization_version,
            collector=full_name(harvest.collector),
            green_weight_kg=harvest.green_weight_kg,
        ),
    )


def created_stage(lot) -> LotHistoryStage:
    account = lot.created_by
    return LotHistoryStage.at(
        "lot_created",
        lot.created_at,
        recorded_at=lot.created_at,
        data=LotCreatedData(created_by=None if account is None else full_name(account)),
    )
