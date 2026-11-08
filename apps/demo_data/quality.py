"""La calidad de los lotes de La Esperanza: la cuenta del Encargado de calidad y un lote en cada
estado. El lote que el secado deja Seco queda para evaluarlo en vivo; aquí se suman uno Evaluado
(para clasificarlo o descartarlo en vivo), uno Clasificado con una parte descartada por moho y uno
Descartado completo, cuyo aviso le llega al Productor.

Cada lote sale de una cosecha nueva, fermentada en el cajón grande y secada en la primera
marquesina libre, que vuelven a quedar libres. Todo pasa por los servicios de cada app.

Los tres lotes se crean una sola vez: si la finca ya tiene alguna evaluación, no se tocan. Lo que
sí se repite es dejar al menos un lote Seco y uno Evaluado, para poder repetir la demostración.
"""

import uuid
from decimal import Decimal

from apps.accounts.models import User
from apps.accounts.system_roles import QUALITY_MANAGER, get_system_role
from apps.accounts.users.creation import create_account
from apps.drying.services.finish import finish_drying
from apps.facilities.models import PostharvestFacility
from apps.lots.choices import LotStatus
from apps.lots.models import Lot
from apps.plots.models import Plot
from apps.quality.models import QualityEvaluation
from apps.quality.services.classification import classify_lot
from apps.quality.services.discard import discard_lot
from apps.quality.services.evaluation import record_evaluation

from .catalog import DEMO_QUALITY_MANAGER
from .drying import at_day, fermented_lot, free_box, log_day, start_in_dryer

QUALITY_LOT_KG = Decimal("300")
# El 38 % del peso en verde, como el lote seco del secado.
QUALITY_DRY_KG = Decimal("114.0")


def seed_quality(owner: User, foreman: User, plot: Plot, restore_account) -> list[str]:
    inspector = _quality_manager(owner, restore_account)
    farm = plot.farm
    notes = []
    if not QualityEvaluation.objects.filter(lot__harvest__plot__farm=farm).exists():
        notes += _quality_lots(owner, foreman, inspector, plot)
    if not _lots(farm, LotStatus.EVALUATED).exists():
        lot = _dried_lot(owner, foreman, plot, harvest_days_ago=24)
        if lot is not None:
            _evaluate(inspector, lot, "82.0", "1.5", "3.0")
            notes.append(f"Calidad: {lot.code} evaluado para clasificar en vivo")
    if not _lots(farm, LotStatus.DRIED).exists():
        lot = _dried_lot(owner, foreman, plot, harvest_days_ago=22)
        if lot is not None:
            notes.append(f"Calidad: {lot.code} seco para evaluar en vivo")
    return notes


def _quality_manager(owner: User, restore_account) -> User:
    """El Encargado de calidad, con alcance en todas las fincas del productor. Se crea una vez; la
    contraseña pública se le restablece siempre."""
    user = User.objects.filter(email__iexact=DEMO_QUALITY_MANAGER["email"]).first()
    if user is None:
        data = DEMO_QUALITY_MANAGER | {
            "role_ids": [get_system_role(QUALITY_MANAGER).pk],
            "all_farms": True,
        }
        user = create_account(owner, data, uuid.uuid4()).user
    restore_account(user, QUALITY_MANAGER)
    return user


def _quality_lots(owner, foreman, inspector, plot) -> list[str]:
    evaluated = _dried_lot(owner, foreman, plot, harvest_days_ago=30)
    classified = _dried_lot(owner, foreman, plot, harvest_days_ago=28)
    discarded = _dried_lot(owner, foreman, plot, harvest_days_ago=26)
    if None in (evaluated, classified, discarded):
        return []
    _evaluate(inspector, evaluated, "82.0", "1.5", "3.0")
    _evaluate(inspector, classified, "78.5", "2.0", "4.5")
    classify_lot(
        inspector,
        classified.pk,
        {
            "expected_lot_version": _version(classified),
            "g1_kg": Decimal("90.0"),
            "g2_kg": Decimal("18.0"),
            "discard_kg": Decimal("6.0"),
            "discard_reason": "mold",
            "discard_detail": "",
        },
    )
    _evaluate(inspector, discarded, "40.0", "22.0", "10.0", notes="Moho en buena parte del corte")
    discard_lot(
        inspector,
        discarded.pk,
        {
            "expected_lot_version": _version(discarded),
            "reason": "mold",
            "detail": "Moho visible en el 22 % de los granos",
        },
    )
    return [
        f"Calidad: {evaluated.code} evaluado, {classified.code} clasificado con descarte por "
        f"moho y {discarded.code} descartado"
    ]


def _dried_lot(owner, foreman, plot, *, harvest_days_ago: int) -> Lot | None:
    """Una cosecha fermentada cinco días y secada cinco en la primera marquesina libre, con su
    peso seco. Sin cajón o sin marquesina libres, no se crea."""
    box = free_box(plot.farm)
    dryer = _free_dryer(plot.farm)
    if box is None or dryer is None:
        return None
    lot = fermented_lot(
        owner, foreman, plot, box, harvest_days_ago=harvest_days_ago, weight=QUALITY_LOT_KG
    )
    # La fermentación termina la madrugada del sexto día después de iniciar: se seca desde esa
    # tarde.
    first_day = harvest_days_ago - 6
    start_in_dryer(foreman, lot, dryer, at_day(first_day, 14))
    readings = (("50.0", "4.0"), ("36.0", "8.0"), ("21.0", "7.0"), ("11.0", "9.0"), ("7.1", "6.0"))
    for day, (moisture, sun) in enumerate(readings):
        log_day(foreman, lot, at_day(first_day - day, 17 if day == 0 else 16), moisture, sun)
    finish_drying(
        owner,
        lot.pk,
        1,
        {
            "ended_at": at_day(first_day - 4, 18),
            "final_moisture_pct": Decimal("7.0"),
            "dry_weight_kg": QUALITY_DRY_KG,
        },
    )
    return Lot.objects.get(pk=lot.pk)


def _evaluate(inspector, lot, well_fermented, moldy, other_defects, notes="") -> None:
    record_evaluation(
        inspector,
        lot.pk,
        {
            "expected_lot_version": _version(lot),
            "well_fermented_pct": Decimal(well_fermented),
            "moldy_pct": Decimal(moldy),
            "other_defects_pct": Decimal(other_defects),
            "notes": notes,
        },
    )


def _version(lot) -> int:
    return Lot.objects.values_list("version", flat=True).get(pk=lot.pk)


def _lots(farm, status):
    return Lot.objects.filter(harvest__plot__farm=farm, status=status)


def _free_dryer(farm) -> PostharvestFacility | None:
    return (
        PostharvestFacility.objects.filter(
            farm=farm, facility_type="solar_dryer", is_active=True, current_lot__isnull=True
        )
        .order_by("name_normalized")
        .first()
    )
