"""La bodega de La Esperanza: una bodega por finca del productor de demostración y lotes en
distintos momentos. El lote Clasificado que deja calidad queda por ingresar en vivo; aquí se suman
uno En bodega con una salida por muestra, otra anulada y un cambio de estante, y otro con el G2
agotado.

Cada lote nuevo sale de una cosecha fermentada y secada como los de calidad, y se evalúa, clasifica
e ingresa por los servicios de cada app. Los lotes En bodega se crean una sola vez: si la finca ya
tiene algún ingreso, no se tocan. Lo que sí se repite es dejar al menos un lote Clasificado por
ingresar y uno En bodega con existencias, para poder repetir la demostración.
"""

from decimal import Decimal

from django.db.models import Q
from django.utils import timezone

from apps.accounts.models import User
from apps.farms.models import Farm
from apps.lots.choices import LotStatus
from apps.lots.models import Lot
from apps.plots.models import Plot
from apps.quality.services.classification import classify_lot
from apps.warehouse.models import StockBalance, StockEntry, Warehouse
from apps.warehouse.services.entry import register_entry
from apps.warehouse.services.exits import register_exit, void_exit
from apps.warehouse.services.moves import move_stock
from apps.warehouse.services.warehouses import create_warehouse

from .catalog import DEMO_QUALITY_EMAIL
from .quality import QUALITY_DRY_KG, _dried_lot, _evaluate, _version

WAREHOUSE_NAME = "Bodega principal"
WAREHOUSE_NAME_NORMALIZED = "bodegaprincipal"


def seed_warehouse(owner: User, foreman: User, plot: Plot) -> list[str]:
    inspector = User.objects.filter(email__iexact=DEMO_QUALITY_EMAIL).first()
    if inspector is None:
        return []
    _warehouses(owner)
    farm = plot.farm
    warehouse = Warehouse.objects.get(farm=farm, name_normalized=WAREHOUSE_NAME_NORMALIZED)
    notes = []
    if not StockEntry.objects.filter(lot__harvest__plot__farm=farm).exists():
        notes += _stored_lots(owner, foreman, inspector, plot, warehouse)
    if not StockBalance.objects.filter(lot__harvest__plot__farm=farm, quantity_kg__gt=0).exists():
        lot = _stored_lot(owner, foreman, inspector, plot, warehouse, harvest_days_ago=16)
        if lot is not None:
            notes.append(f"Bodega: {lot.code} en bodega con existencias")
    if not _pending_entry(farm).exists():
        lot = _classified_lot(owner, foreman, inspector, plot, harvest_days_ago=14)
        if lot is not None:
            notes.append(f"Bodega: {lot.code} clasificado para ingresar en vivo")
    return notes


def _warehouses(owner: User) -> None:
    """Una bodega por cada finca del productor de demostración, para ingresar en cualquiera."""
    for farm in Farm.objects.filter(producer=owner.producer):
        if not Warehouse.objects.filter(farm=farm, name_normalized=WAREHOUSE_NAME_NORMALIZED):
            create_warehouse(owner, {"farm_id": farm.pk, "name": WAREHOUSE_NAME})


def _stored_lots(owner, foreman, inspector, plot, warehouse) -> list[str]:
    with_exits = _stored_lot(
        owner,
        foreman,
        inspector,
        plot,
        warehouse,
        harvest_days_ago=20,
        grades=("100.0", "14.0"),
    )
    depleted = _stored_lot(
        owner,
        foreman,
        inspector,
        plot,
        warehouse,
        harvest_days_ago=18,
        grades=("96.0", "18.0"),
        location="Estante 2",
    )
    if with_exits is None or depleted is None:
        return []
    today = timezone.localdate()
    register_exit(
        inspector,
        with_exits.pk,
        {
            "grade": "g1",
            "quantity_kg": Decimal("2.0"),
            "exit_date": today,
            "reason": "sample",
            "detail": "",
        },
    )
    mistaken = register_exit(
        inspector,
        with_exits.pk,
        {
            "grade": "g2",
            "quantity_kg": Decimal("1.5"),
            "exit_date": today,
            "reason": "shrinkage",
            "detail": "",
        },
    )
    void_exit(inspector, with_exits.pk, mistaken.pk, "Error de digitación: era otro lote")
    entry = StockEntry.objects.get(lot=with_exits)
    move_stock(
        inspector,
        with_exits.pk,
        entry.version,
        warehouse_id=warehouse.pk,
        location="Estante 2",
    )
    register_exit(
        inspector,
        depleted.pk,
        {
            "grade": "g2",
            "quantity_kg": Decimal("18.0"),
            "exit_date": today,
            "reason": "reprocessing",
            "detail": "",
        },
    )
    return [
        f"Bodega: {with_exits.code} en bodega con una salida por muestra, una anulada y un cambio "
        f"de estante, y {depleted.code} con el G2 agotado"
    ]


def _classified_lot(
    owner, foreman, inspector, plot, *, harvest_days_ago, grades=("100.0", "14.0")
) -> Lot | None:
    """Una cosecha seca, evaluada y clasificada sin descarte. Sin cajón o sin marquesina libres, no
    se crea."""
    lot = _dried_lot(owner, foreman, plot, harvest_days_ago=harvest_days_ago)
    if lot is None:
        return None
    _evaluate(inspector, lot, "80.0", "2.0", "4.0")
    g1, g2 = Decimal(grades[0]), Decimal(grades[1])
    assert g1 + g2 == QUALITY_DRY_KG
    classify_lot(
        inspector,
        lot.pk,
        {
            "expected_lot_version": _version(lot),
            "g1_kg": g1,
            "g2_kg": g2,
            "discard_kg": Decimal("0.0"),
            "discard_reason": "",
            "discard_detail": "",
        },
    )
    return Lot.objects.get(pk=lot.pk)


def _stored_lot(
    owner,
    foreman,
    inspector,
    plot,
    warehouse,
    *,
    harvest_days_ago,
    grades=("100.0", "14.0"),
    location="Estante 1",
) -> Lot | None:
    lot = _classified_lot(
        owner, foreman, inspector, plot, harvest_days_ago=harvest_days_ago, grades=grades
    )
    if lot is None:
        return None
    register_entry(
        inspector,
        lot.pk,
        {
            "expected_lot_version": _version(lot),
            "entry_date": timezone.localdate(),
            "warehouse_id": warehouse.pk,
            "location": location,
        },
    )
    return Lot.objects.get(pk=lot.pk)


def _pending_entry(farm):
    """Los lotes Clasificado de la finca con algo que ingresar."""
    return Lot.objects.filter(
        Q(classification__g1_kg__gt=0) | Q(classification__g2_kg__gt=0),
        harvest__plot__farm=farm,
        status=LotStatus.CLASSIFIED,
    )
